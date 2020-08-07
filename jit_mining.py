import sys
import argparse
import logging
import datetime

import pandas as pd

from util.traversal import Traversal

log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)


def get_project(project_path, file_check):
    keywords = ["fix", "bug", "repair", "issue", "error"]  # Keywords used by Pascarella et al.
    to_date = datetime.datetime(2017, 12, 31, 23, 59, 59)

    t = Traversal(project_path, file_check, log, to_date, keywords)
    return t.start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract JIT DP Data')
    parser.add_argument('--project', help='Name of the project to extract', required=True)
    parser.add_argument('--path', help='Full path of the repository of the project to extract', required=True)
    parser.add_argument('--file-check', help='Check files for each revision against state', required=False, action='store_true')
    args = parser.parse_args()

    data = get_project(args.path, args.file_check)

    df = pd.DataFrame(data)
    df.to_csv('./data/jit_{}.csv'.format(args.project), index=False)
