#! /usr/bin/env python
# -*- coding: utf-8 -*-
# COPYRIGHT: Openmoko Inc. 2010
# LICENSE: GPL Version 3 or later
# DESCRIPTION: Index file combine to build overall index
# AUTHORS: Sean Moss-Pultz <sean@openmoko.com>
#          Christopher Hall <hsw@openmoko.com>

import os, sys, re
import os.path
import struct
import getopt

def usage(message):
    if None != message:
        print('error: {0:s}'.format(message))
    print('usage: {0:s} <options>'.format(os.path.basename(__file__)))
    print('       --help                  This message')
    print('       --verbose               Enable verbose output')
    print('       --prefix=name           Device file name portion for .idx [pedia]')
    exit(1)

def main():
    global verbose
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hvo:f:p:', ['help', 'verbose', 'out=', 'offsets=', 'prefix='])
    except getopt.GetoptError, err:
        usage(err)

    verbose = False
    in_format = 'pedia{0:d}.idx-tmp'
    out_name = 'pedia.idx'

    for opt, arg in opts:
        if opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-h', '--help'):
            usage(None)
            off_name = arg
        elif opt in ('-p', '--prefix'):
            in_format = arg + '{0:d}.idx-tmp'
            out_name = arg + '.idx'
        else:
            usage('unhandled option: ' + opt)

    out = open(out_name, 'wb')

    article_count = 0
    i = 0
    data = {}
    while True:
        in_name = in_format.format(i)
        if not os.path.isfile(in_name):
            break
        if verbose:
            print('combining: {0:s}'.format(in_name))
        data[i] = open(in_name, 'rb').read()
        article_count += len(data[i]) / 12 # sizeof(struct)
        i += 1

    out.write(struct.pack('I', article_count))

    for j in range(i):
        out.write(data[j])

    out.close()


# run the program
if __name__ == "__main__":
    main()
