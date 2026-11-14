#!/usr/bin/env python3
"""Measure a verified synthetic fixture; save private observations exclusively."""
import argparse
import json
import sqlite3
from recaplib.benchmark import run_benchmark


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture_dir')
    parser.add_argument('--work-dir',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--repetitions',type=int,default=1)
    args=parser.parse_args(argv)
    try:
        result=run_benchmark(args.fixture_dir,args.work_dir,args.output,args.repetitions)
    except (ValueError,OSError,TypeError,KeyError,sqlite3.Error,RecursionError):
        parser.exit(1,'Benchmark failed. Newly created scratch files may remain; inspect them and use fresh paths before retrying.\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
