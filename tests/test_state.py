"""Tests for storing and loading of state."""
import unittest
import tempfile
import subprocess
import logging
import sys
import os
import datetime

from util.traversal import Traversal, TraversalState
from util.config import Config

from pprint import pprint

# disable logging for tests
logging.disable(logging.CRITICAL)

# but in case we need it configure it here
log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)


class Args():
    """Default config object we use for these tests."""
    language = 'java'
    connector = None
    production_only = False
    use_linter = False
    use_maven = False
    quality_keywords = {}
    project = 'tmp'
    file_check = True
    is_test = True
    keywords = ['fix']
    to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)


class TestTraversalState(unittest.TestCase):
    """Test state storing and loading."""

    def test_saving_loading(self):
        """test continuation of jit mining"""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/state1.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE, check=True)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)

            # save state
            state_file = '/tmp/test.pickle'
            ts.save(state_file)
            # pprint(files)

            # print('ts1', ts.need_commits)
            self.assertEqual(files[0]['la'], 5)  # add 5 lines in first commit and file
            self.assertEqual(files[0]['adhoc__76c75e92b3ec59e9f053b18afafa6fc2b349ebec__2018-01-03 03:01:01+02:00'], 1)
            # self.assertEqual(files)

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/state2.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE, check=True)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts1 = TraversalState.load(state_file)
            ts2 = t.update_graph(ts1)

            #print('ts1', ts1.need_commits)
            #print('ts2', ts2.need_commits)
            files2 = t.traverse(ts2)

            self.assertEqual(files2[0]['la'], 5)
            self.assertEqual(files2[0]['adhoc__76c75e92b3ec59e9f053b18afafa6fc2b349ebec__2018-01-03 03:01:01+02:00'], 1)
            self.assertEqual(files2[2]['adhoc__7d85669720bc0272564efc0d8562645723372600__2019-02-04 03:01:01+02:00'], 1)
            # pprint(files2)
