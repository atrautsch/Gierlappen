"""Tests for the feature extraction."""
import unittest
import tempfile
import subprocess
import logging
import datetime
import sys
import pytz

from pprint import pprint
from util.traversal import Traversal

log = logging.getLogger('jit')
log.setLevel(logging.DEBUG)
i = logging.StreamHandler(sys.stdout)
e = logging.StreamHandler(sys.stderr)

i.setLevel(logging.DEBUG)
e.setLevel(logging.ERROR)

log.addHandler(i)
log.addHandler(e)

log = logging.getLogger()

class TestFeatures(unittest.TestCase):

    def test_basic_jit_features(self):
        """Test line count adding."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/features.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            keywords = ["fix"]
            to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)

            t = Traversal(tmpdirname, True, log, to_date, keywords, is_test=True)
            files = t.start()
            # pprint(files)

            self.assertEqual(files[0]['la'], 5)  # add 5 lines in first commit and file
            self.assertEqual(files[1]['la'], 1)
            self.assertEqual(files[1]['ld'], 1)
            self.assertEqual(files[1]['file'], 'Main.java')
            self.assertEqual(files[2]['la'], 4)
            self.assertEqual(files[2]['file'], 'Test.java')

            # first author introdouced Main.java and is its owner, second author not
            self.assertTrue(files[0]['own'])
            self.assertFalse(files[1]['own'])

            # after editing the file has two authors
            self.assertEqual(files[1]['ddev'], 2)

            # age is retained after rename
            # age is the number of days after the last change
            self.assertEqual(files[1]['file'], 'Main.java')
            self.assertEqual(abs(files[1]['committer_date'] - datetime.datetime(2018, 1, 3, 1, 1, 1, tzinfo=pytz.UTC)), datetime.timedelta(seconds=0))

            self.assertEqual(files[3]['file'], 'Rubbish.java')
            self.assertEqual(abs(files[3]['committer_date'] - datetime.datetime(2018, 1, 4, 1, 1, 1, tzinfo=pytz.UTC)), datetime.timedelta(seconds=0))
            self.assertEqual(files[3]['age'], 1)  # 1 day after last change with old name (files[2] was Test.java)
