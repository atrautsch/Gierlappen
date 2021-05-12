"""Tests for the pylint extraction."""
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
log = logging.getLogger('none')
# log = logging.getLogger('jit')
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
    language = 'python'
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


class TestPylint(unittest.TestCase):

    def test_pylint(self):
        """Test pylint"""

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/pylint1.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            # pprint(files)
            self.assertEqual(files[0]['current_WD'], 1.3333333333333333)
            # pprint(files)
