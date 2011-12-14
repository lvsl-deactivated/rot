#!/usr/bin/env python
# coding: utf-8

#
# R.O.T - Rotate Outputs To ...
#

# XXX: -u turns off std{out,err,in} buffering
# and set binary mode (see man page for details)

import os
import sys

from optparse import OptionParser
from collections import namedtuple



class RotError(Exception): pass



Opts = namedtuple('Opts',
                  'out_file out_count out_limit err_file err_count err_limit args')



class Validator(object):

    def __init__(self):
        self.validators = {
            'count': self._validate_count,
            'file':  self._validate_file,
            'limit': self._validate_limit,
            'args':  self._validate_args,
        }

    def __call__(self, v, t):
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
        if type(count) != int:
            self.err_msg = 'Wrong type for count: %s' % type(count)
        elif count <= 0:
            self.err_msg = 'Count must be > 0'
        else:
            return count

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
        n = limit[:-1]
        s = limit[-1]
        n2bytes = {
            'B': 1,
            'K': 1024,
            'M': 1024 ** 2,
            'G': 1024 ** 3,
        }
        if s not in n2bytes:
            self.err_msg = 'Incorrent size identificator: %s' % s
        elif not n.isdigit():
            self.err_msg = "%s isn't a digit" % n
        elif n <= 0:
            self.err_msg = "%s must be > 0" % n
        else:
            limit_in_bytes = int(n) * n2bytes[s]

            return limit_in_bytes

    def _validate_args(self, args):
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
    p = OptionParser(usage="%prog [patams] -- <args>")
    p.add_option("--stdout-file",  dest="out_file")
    p.add_option("--stdout-count", dest="out_count", type="int")
    p.add_option("--stdout-limit", dest="out_limit")

    p.add_option("--stderr-file",  dest="err_file")
    p.add_option("--stderr-count", dest="err_count", type="int")
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



def main():
    try:
        opts = read_argv()
    except Exception as e:
        sys.stderr.write("%s\n" % e)
        return 1
    print opts
    return 0



if __name__ == "__main__":
    sys.exit(main())
