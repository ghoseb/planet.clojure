#!/usr/bin/env python3
"""
Planet Venus - a flexible feed aggregator
Requires Python 3.8 or later
"""

import os
import sys
import time
import getopt
import traceback
from io import StringIO
from queue import Queue

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from planet import config, spider, splice
from planet.expunge import expungeCache

def usage():
    print("Usage: planet [options] [CONFIGFILE]")
    print("Options:")
    print("  -h, --help            show this help message and exit")
    print("  -v, --verbose         verbose output")
    print("  -o, --output-dir DIR  output directory")
    print("  -n, --no-publish      do not publish")
    print("  -x, --expunge         expunge cache")
    print("  --no-publish          do not publish")

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvo:nx", 
            ["help", "verbose", "output-dir=", "no-publish", "expunge"])
    except getopt.GetoptError as e:
        print(e)
        usage()
        sys.exit(2)

    verbose = False
    output_dir = None
    no_publish = False
    expunge = False

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-v", "--verbose"):
            verbose = True
        elif opt in ("-o", "--output-dir"):
            output_dir = arg
        elif opt in ("-n", "--no-publish"):
            no_publish = True
        elif opt in ("-x", "--expunge"):
            expunge = True

    if len(args) > 1:
        usage()
        sys.exit(2)

    config_file = args[0] if args else "config.ini"
    if not os.path.isfile(config_file):
        print("Error: %s not found" % config_file)
        sys.exit(1)

    try:
        config.load(config_file)
        if output_dir:
            config.parser.set('Planet', 'output_dir', output_dir)
        if verbose:
            config.parser.set('Planet', 'log_level', 'DEBUG')

        if expunge:
            expungeCache()

        spider.spiderPlanet()
        splice.splicePlanet()

        if not no_publish:
            from planet import publish
            publish.publish.publish(config)

    except Exception as e:
        print("Error: %s" % e)
        if verbose:
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
