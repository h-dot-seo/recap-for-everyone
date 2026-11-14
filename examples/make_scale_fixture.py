#!/usr/bin/env python3
"""Create a bounded deterministic synthetic fixture in a new private directory."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recaplib.benchmark import generate_fixture


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir')
    parser.add_argument('--conversations',type=int,default=50)
    parser.add_argument('--messages',type=int,default=10)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args(argv)
    try:
        result=generate_fixture(args.output_dir,args.conversations,args.messages,args.seed)
    except (ValueError,OSError,TypeError,RecursionError):
        parser.exit(1,'Fixture generation failed. Partial new files may remain; inspect them and use a fresh directory before retrying.\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
