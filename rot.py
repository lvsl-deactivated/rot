# coding: utf-8

'''
  --std[out|err]-file F:  Write [stdout|stderr] to F.
                          Write performs by chunks with flush.

  --std[out|err]-limit L: Limit the size of --std[out|err]-file to L.
                          Available size types: B, K, M, G.

  --std[out|err]-count N: Works iff --std[out|err]-limit is set.
                          If size of F > L then rotate F no more than N times.

Example:
  %prog --stdout-file ~/out.txt --stdout-count 4 --stdout-limit 100M \\
  -- spam_program -a -b -c 10
'''

DEBUG = True

import os
import sys
import glob
import errno
import fcntl
import threading
import subprocess

from optparse import OptionParser
from collections import namedtuple



class RotError(Exception): pass



Opts = namedtuple('Opts',
                  'out_file out_count out_limit err_file err_count err_limit args')



class Validator(object):
    '''\
    Django-style command line parameters validation.
    '''

    def __init__(self):
        self.validators = {
            'count': self._validate_count,
            'file':  self._validate_file,
            'limit': self._validate_limit,
            'args':  self._validate_args,
        }

    def __call__(self, v, t):
        '''\
        Validate value `v` with validator `t`
        '''

        if t not in self.validators:
            raise RotError("Unknown validator: %s" % t)
        elif v is None:
            return
        self.err_msg = ''
        valid_v = self.validators[t](v)
        if self.err_msg:
            raise RotError(self.err_msg)
        return valid_v

    def _validate_count(self, count):
        try:
            c = int(count)
        except (ValueError, TypeError):
            self.err_msg = "Can't convert %s to int" % count
            return
        if c <= 0:
            self.err_msg = 'Count must be > 0'
        else:
            return c

    def _validate_file(self, path_to_file):
        abs_path_to_file = os.path.abspath(os.path.expanduser(path_to_file))
        d = os.path.dirname(abs_path_to_file)
        if os.path.exists(abs_path_to_file):
            self.err_msg = "File %s already exists" % abs_path_to_file
        elif not os.path.exists(d):
            self.err_msg = "Directory '%s' doesn't exists" % d
        elif not os.access(d, os.W_OK):
            self.err_msg = "%s isn't write accessible" % d
        else:
            return abs_path_to_file

    def _validate_limit(self, limit):
        sn = limit[:-1]
        s = limit[-1]
        n2bytes = {
            'B': 1,
            'K': 1024,
            'M': 1024 ** 2,
            'G': 1024 ** 3,
        }
        if s not in n2bytes:
            self.err_msg = 'Incorrent size identificator: %s' % s
            return

        try:
            n = int(sn)
        except (ValueError, TypeError):
            self.err_msg = "Can't convert %s to int" % sn
            return

        if n <= 0:
            self.err_msg = "%s must be > 0" % n
        else:
            limit_in_bytes = int(n) * n2bytes[s]

            return limit_in_bytes

    def _validate_args(self, args):
        '''\
        Args is the program from which we rediret stdout/stderr
        Here we try to find absolute path to this program
        using unix's which like logic.
        '''
        def which(program):
            ''' taken from http://stackoverflow.com/a/377028 '''
            def is_exe(fpath):
                return os.path.exists(fpath) and os.access(fpath, os.X_OK)

            fpath, fname = os.path.split(program)
            if fpath:
                if is_exe(program):
                    return program
            else:
                for path in os.environ["PATH"].split(os.pathsep):
                    exe_file = os.path.join(path, program)
                    if is_exe(exe_file):
                        return exe_file

            return None
        if not args:
            self.err_msg = "No program to run"
        elif not which(args[0]):
            self.err_msg = "can't find %s or it is not an executable" % args[0]
        else:
            return args



def validate_file(f):
    v = Validator()
    return v(f, 'file')



def validate_count(c):
    v = Validator()
    return v(c, 'count')



def validate_limit(l):
    v = Validator()
    return v(l, 'limit')



def validate_args(a):
    v = Validator()
    return v(a, 'args')



def read_argv():
    '''\
    Read command-line options with optparse and validate them
    '''

    p = OptionParser(usage=__doc__)
    p.add_option("--stdout-file",  dest="out_file")
    p.add_option("--stdout-count", dest="out_count")
    p.add_option("--stdout-limit", dest="out_limit")

    p.add_option("--stderr-file",  dest="err_file")
    p.add_option("--stderr-count", dest="err_count")
    p.add_option("--stderr-limit", dest="err_limit")

    opts, args = p.parse_args()
    # store needed options as numedtuple
    params = Opts(
        out_file  = validate_file(opts.out_file),
        out_count = validate_count(opts.out_count),
        out_limit = validate_limit(opts.out_limit),
        err_file  = validate_file(opts.err_file),
        err_count = validate_count(opts.err_count),
        err_limit = validate_limit(opts.err_limit),
        args      = validate_args(args)
    )
    return params



class StreamCollector(threading.Thread):

    BUF_SIZE = 1024

    def __init__(self, stream, fname, limit, count, default_stream):
        self.fname = fname
        self.fd_in = self._non_block_fd(stream)
        self.fo = open(fname, 'wb') if fname else default_stream
        self.limit = limit
        self.count = count
        self.default_stream = default_stream
        self.curr_pos = 0

        threading.Thread.__init__(self)

    @staticmethod
    def _non_block_fd(fo):
        fd = fo.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        return fd

    def _list_logs(self):
        """
        Return sorted list of integers - the old logs' identifiers.
        """
        result = []
        for name in glob.glob("%s.*" % self.fname):
            try:
                counter = int(name.split('.')[-1])
                if counter:
                    result.append(counter)
            except ValueError:
                pass
        result.sort()
        return result

    def _read_fd(self):
        buff = os.read(self.fd_in, self.BUF_SIZE)
        if not buff:
            return
        if self.limit:
            d = self.limit - self.curr_pos
            if d > 0:
                l = len(buff)
                self.fo.write(buff[:d])
                self.fo.flush()
                # if count is present and buffer don't fit
                # in file limit then rotate logs
                if self.count and l > d:
                    log_files = self._list_logs()
                    log_files.reverse()
                    for i in log_files:
                        if i >= self.count:
                            os.remove('%s.%d' % (self.fname, i))
                        else:
                            os.rename('%s.%d' % (self.fname, i), '%s.%d' % (self.fname, i+1))
                    self.fo.close()
                    os.rename(self.fname, '%s.1' % self.fname)
                    self.fo = open(self.fname, 'wb')
                    self.fo.write(buff[d:])
                    self.curr_pos = 0
                else:
                    self.curr_pos += l
        else:
            self.fo.write(buff)
            self.fo.flush()
        return buff

    def run(self):
        while True:
            try:
                if not self._read_fd():
                    break
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    raise

        if self.fo != self.default_stream:
            self.fo.close()



def run_program(opts):
    subp_params = {
        'shell': True,
        'stdin': sys.stdin,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
    }

    p = subprocess.Popen(' '.join(opts.args), **subp_params)

    out_thread = StreamCollector(p.stdout, opts.out_file, opts.out_limit, opts.out_count, sys.stdout)
    err_thread = StreamCollector(p.stderr, opts.err_file, opts.err_limit, opts.err_count, sys.stderr)

    out_thread.start()
    err_thread.start()

    p.wait()

    out_thread.join()
    err_thread.join()

    return p.returncode



def main():
    '''\
    Run program.
    Call this method from your scripts
    '''
    try:
        opts = read_argv()
        exit_code = run_program(opts)
        return exit_code
    except Exception as e:
        if DEBUG:
            msg = e
        else:
            msg = e.message
        sys.stderr.write("%s\n" % msg)
        return 1
