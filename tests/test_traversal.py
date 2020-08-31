"""Tests for the traversal part of Gierlappen."""
import unittest
import tempfile
import subprocess
import logging
import datetime
import sys

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

class TestTraversal(unittest.TestCase):

    def test_rename_bug(self):
        """Test for rename tracking.
        Main.java is inducing an error before beeing renamed to Rubbish.java
        We want to be able to trace the bugfix in Rubbish.java to Main.java.
        """
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/rename.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            keywords = ["fix"]
            to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)

            t = Traversal(tmpdirname, True, log, to_date, keywords, is_test=True)
            files = t.start()
            # pprint(files)

            inducing = files[1]
            fixing = files[3]
            self.assertEqual(inducing['file'], 'Main.java')
            self.assertEqual(inducing['adhoc__d2b5b919ce03809c3d07b7f1cd647c6a69fa5c93__2018-01-05 03:01:01+02:00'], 1)
            self.assertEqual(fixing['file'], 'Rubbish.java')
            self.assertEqual(fixing['fix_bug'], True)
            self.assertEqual(fixing['adhoc__d2b5b919ce03809c3d07b7f1cd647c6a69fa5c93__2018-01-05 03:01:01+02:00'], 0)

    def test_rename_accumulating_features(self):
        """Test for retaining of accumulating file metrics after rename.
        Main.java is renamed to Rubbish.java, we check if it retains the metrics.
        """

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/rename.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            keywords = ["fix"]
            to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)

            t = Traversal(tmpdirname, True, log, to_date, keywords, is_test=True)
            files = t.start()
            self.assertEqual(files[3]['comm'], 4)  # 4 commits, 2 when named Main.java and 2 after rename to Rubbish.java
            # pprint(files)

