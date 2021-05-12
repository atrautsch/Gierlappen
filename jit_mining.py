"""Entrypoint for just-in-time defect prediction data mining without smartshark dependency."""

import os
import sys
import argparse
import logging
import datetime

import pandas as pd

from util.traversal import Traversal, TraversalState
from util.config import Config

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

i.setFormatter(formatter)
e.setFormatter(formatter)

i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)


def get_project(args):
    keywords = ["fix", "bug", "repair", "issue", "error"]  # Keywords used by Pascarella et al.
    to_date = datetime.datetime(2017, 12, 31, 23, 59, 59)
    to_date = datetime.datetime.now()

    args.all_branches = False
    args.is_test = False
    args.use_maven = False
    args.quality_keywords = {}
    args.keywords = keywords
    args.to_date = to_date
    args.connector = None

    c = Config(args)

    # todo: can we do this in a nicer way?
    t = Traversal(c)
    if args.state_file and os.path.isfile(args.state_file):
        ts1 = TraversalState.load(args.state_file)
        ts = t.update_graph(ts1)
    else:
        ts = t.create_graph()

    data = t.traverse(ts)

    if args.state_file:
        ts.save(args.state_file)

    return data

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract JIT DP Data')
    parser.add_argument('--project', help='Name of the project to extract', required=True)
    parser.add_argument('--path', help='Full path of the repository of the project to extract', required=True)
    parser.add_argument('--language', help='Project main language, e.g., python, java', required=True)
    parser.add_argument('--state-file', help='Save state to this file to later continue from.', required=False)
    parser.add_argument('--file-check', help='Check files for each revision against state', required=False, action='store_true')
    parser.add_argument('--production-only', help='Restrict all files to production code', required=False, action='store_true')
    parser.add_argument('--use-linter', help='Collects Linter information for each changed file', required=False, action='store_true')
    args = parser.parse_args()

    data = get_project(args)

    df = pd.DataFrame(data)
    df.to_csv('./data/jit_{}.csv'.format(args.project), index=False)
