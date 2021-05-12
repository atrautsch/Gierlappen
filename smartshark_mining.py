"""Entrypoint for mining just-in-time defect prediction data with the smartshark database."""

import sys
import os
import argparse
import logging
import datetime

import pandas as pd

from connectors.smartshark import SmartSharkConnector
from util.traversal import Traversal
from util.config import Config

QUALITY_KEYWORDS = {'generic': ['obsolete', 'renamed', 'cleaning', 'cleanup', 'clean up', 'cleaned up', 'cleanups', 'unused',
                                'deprecated', 'unnecessary', 'refactoring', 'refactor', 'formatting', 'generics', 'simplify', 'unnecessarily',
                                'non necessary', 'removal', 'removed', 'imports', 'improve', 'remove old', 'refinements'],
                    'asat': ['error-prone', 'infer', 'pmd', 'findbugs', 'spotbugs', 'checkstyle', 'sonarcube'],
                    'factor': ['readability', 'maintainability', 'complexity'],
                    'pantiuchina': ['readability', 'cohesion', 'complexity', 'coupling']}

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

    con = SmartSharkConnector(args.project, args.path, args.production_only, args.labels, args.db_host, args.db_port, args.db_name, args.db_user, args.db_pw, args.db_auth)

    args.all_branches = False
    args.is_test = False
    args.connector = con
    args.quality_keywords = QUALITY_KEYWORDS
    args.keywords = keywords
    args.to_date = to_date
    args.language = 'java'

    if args.use_linter:
        args.pmd_path = os.path.abspath('./checks/pmd/')

    c = Config(args)

    t = Traversal(c)
    ts = t.create_graph()
    return t.traverse(ts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract JIT DP Data')
    parser.add_argument('--project', help='Name of the project to extract', required=True)
    parser.add_argument('--path', help='Full path of the repository of the project to extract', required=True)
    parser.add_argument('--file-check', help='Check files for each revision against state', required=False, action='store_true')
    parser.add_argument('--use-maven', help='Include Maven information', required=False, action='store_true')
    parser.add_argument('--use-linter', help='Collects PMD information for each changed file', required=False, action='store_true')

    # additional smartshark related information
    parser.add_argument('--production-only', help='Restrict all files to production code', required=False, action='store_true')
    parser.add_argument('--labels', help='Smartshark labels for bug-inducing, can be comma separated, e.g., JL+R,JLMIV+R', required=True, default='JL+R,JLMIV+R')

    parser.add_argument('--db-host', help='Database host', required=True)
    parser.add_argument('--db-port', help='Database port', required=True)
    parser.add_argument('--db-name', help='Database name', required=True)
    parser.add_argument('--db-user', help='Database user', required=True)
    parser.add_argument('--db-pw', help='Database pw', required=True)
    parser.add_argument('--db-auth', help='Database authentication source', required=True)

    parser.add_argument('--pg-host', help='Postgresql Database host')
    parser.add_argument('--pg-port', help='Postgresql Database port')
    parser.add_argument('--pg-name', help='Postgresql Database name')
    parser.add_argument('--pg-user', help='Postgresql Database user')
    parser.add_argument('--pg-pw', help='Postgresql Database pw')
    parser.add_argument('--pg-schema', help='Postgresql Database schema name')
    args = parser.parse_args()

    data = get_project(args)

    df = pd.DataFrame(data)
    name = '{}_{}'.format(args.project, args.labels)
    if args.production_only:
        name += '_production'
    if args.use_linter:
        name += '_pmd6'

    df.to_csv('./data/jit_sn_{}.csv'.format(name), index=False)
