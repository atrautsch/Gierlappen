import sys
import argparse
import logging
import datetime

import pandas as pd

from util.smartshark_connector import SmartSharkConnector
from util.traversal import Traversal

QUALITY_KEYWORDS = {'generic': ['obsolete', 'renamed', 'cleaning', 'cleanup', 'clean up', 'cleaned up', 'cleanups', 'unused',
                                'deprecated', 'unnecessary', 'refactoring', 'refactor', 'formatting', 'generics', 'simplify', 'unnecessarily',
                                'non necessary', 'removal', 'removed', 'imports', 'improve', 'remove old', 'refinements'],
                    'asat': ['error-prone', 'infer', 'pmd', 'findbugs', 'spotbugs', 'checkstyle', 'sonarcube'],
                    'factor': ['readability', 'maintainability', 'complexity'],
                    'pantiuchina': ['readability', 'cohesion', 'complexity', 'coupling']}

log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)


def get_project(args):
    keywords = ["fix", "bug", "repair", "issue", "error"]  # Keywords used by Pascarella et al.
    to_date = datetime.datetime(2017, 12, 31, 23, 59, 59)

    con = SmartSharkConnector(args.project, args.path, log, args.regex_only, args.jira_key, args.label_name, args.db_host, args.db_port, args.db_name, args.db_user, args.db_pw, args.db_auth)

    t = Traversal(args.path, args.file_check, log, to_date, keywords, QUALITY_KEYWORDS, con)
    return t.start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract JIT DP Data')
    parser.add_argument('--project', help='Name of the project to extract', required=True)
    parser.add_argument('--path', help='Full path of the repository of the project to extract', required=True)
    parser.add_argument('--file-check', help='Check files for each revision against state', required=False, action='store_true')

    # additional smartshark related information
    parser.add_argument('--regex-only', help='Use simple bug labels instead of JLMIV+R (or other passed label-name)', required=False, action='store_true')
    parser.add_argument('--jira-key', help='JIRA key of the project', required=False)
    parser.add_argument('--label-name', help='Smartshark label for bug-inducing', required=True, default='JLMIV+R')

    parser.add_argument('--db-host', help='Database host', required=True)
    parser.add_argument('--db-port', help='Database port', required=True)
    parser.add_argument('--db-name', help='Database name', required=True)
    parser.add_argument('--db-user', help='Database user', required=True)
    parser.add_argument('--db-pw', help='Database pw', required=True)
    parser.add_argument('--db-auth', help='Database authentication source', required=True)

    args = parser.parse_args()

    data = get_project(args)

    df = pd.DataFrame(data)
    df.to_csv('./data/jit_sn_{}.csv'.format(args.project), index=False)
