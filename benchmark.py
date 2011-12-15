#!/usr/bin/env python
# coding: utf-8

"""
Bechmark stdout redirect.
Example:
  %prog -l 1000 -a 1000 -s 1
"""

import sys
import time

from optparse import OptionParser
from collections import namedtuple



class BenchError(Exception): pass



Opts = namedtuple('Opts',
                  'length amount sleep_interval')



def read_options():
    p = OptionParser(usage=__doc__)
    p.add_option('-l', '--length', dest="l", type="int", default=80)
    p.add_option('-a', '--amount', dest="a", type="int", default=100)
    p.add_option('-s', '--sleep_interval', dest="s", type="float", default=0.1)

    opts, _ = p.parse_args()

    params = Opts(
        length=opts.l,
        amount=opts.a,
        sleep_interval=opts.s
    )

    return params



def emit_stdout(opts):
    for i in range(opts.amount):
        sys.stdout.write('x' * opts.length)
        sys.stdout.write('\n')
        sys.stdout.flush()
        time.sleep(opts.sleep_interval)



def main():
    opts = read_options()
    emit_stdout(opts)
    return 0

if __name__ == "__main__":
    sys.exit(main())
