"""Tests for the feature extraction."""
import unittest
import os
import tempfile
import subprocess
import logging
import datetime
import sys

from pprint import pprint
from util.traversal import Traversal
from util.config import Config

# usually we want silence in here
# log = logging.getLogger('none')
log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
i.setFormatter(formatter)
e.setFormatter(formatter)
i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)


class Args():
    """Default config object we use for these tests."""
    language = 'java'
    connector = None
    production_only = False
    use_linter = True
    use_maven = False
    quality_keywords = {}
    project = 'tmp'
    file_check = True
    is_test = True
    keywords = ['fix']
    to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)
    pmd_path = os.path.abspath('./checks/pmd/')


class TestPMD(unittest.TestCase):

    def test_pmd6(self):
        """Test PMD."""

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/features2.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            # pprint(files)

            added1 = ['NoPackage',
                      'UseUtilityClass',
                      'ShortClassName',
                      'CommentRequired',
                      'UncommentedEmptyMethodBody',
                      'MethodArgumentCouldBeFinal',
                      'CommentRequired']
            file1_current_wd = 7 / 2  # lloc from pycount does not count single }
            system_wd = 2.8

            step2_file_current_wd = 7 / 3
            step2_system_wd = 2.625
            step2_parent_system_wd = system_wd

            self.assertEqual(files[0]['linter_parent_warnings'], 0)
            self.assertEqual(files[0]['linter_warnings'], len(added1))
            self.assertEqual(files[0]['linter_added_warnings'], added1)
            self.assertEqual(files[0]['linter_deleted_warnings'], [])
            self.assertEqual(files[0]['linter_lloc'], 5)
            self.assertEqual(files[0]['current_WD'], file1_current_wd)
            self.assertEqual(files[0]['system_WD'], system_wd)
            self.assertEqual(files[0]['author_delta_sum_WD'], system_wd - 0)
            self.assertEqual(files[0]['file_system_sum_WD'], file1_current_wd - system_wd)
            self.assertEqual(files[2]['file_system_sum_WD'], (file1_current_wd - system_wd) + (step2_file_current_wd - step2_system_wd))
            self.assertEqual(files[2]['decayed_file_system_sum_WD'], ((file1_current_wd - system_wd)/2) + ((step2_file_current_wd - step2_system_wd)/1))
            self.assertEqual(files[2]['author_delta_sum_WD'], (step2_system_wd - step2_parent_system_wd))  # this is by another author
            self.assertEqual(files[4]['author_delta_sum_WD'], (system_wd - 0) + (3.0 - 2.625))  # this is the same as the first author
            self.assertEqual(files[4]['decayed_author_delta_sum_WD'], ((system_wd - 0)/2) + ((3.0 - 2.625)/1))
