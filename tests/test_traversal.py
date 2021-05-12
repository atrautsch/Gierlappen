"""Tests for the traversal part of Gierlappen."""
import unittest
import tempfile
import subprocess
import logging
import datetime
import sys
import pytz

from pprint import pprint
from util.traversal import Traversal
from util.config import Config

log = logging.getLogger('none')
# log = logging.getLogger('jit')
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


class TestTraversal(unittest.TestCase):
    """Test basic traversal implementation."""

    def test_file_rename_on_branch(self):
        """Tests the case in which a file was renamed then fixed on a second branch."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/rename_on_branch.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            # pprint(files)

            inducing = files[2]
            fixing = files[4]

            # check path num
            self.assertEqual(files[1]['pathnum'], 0)
            self.assertEqual(files[2]['pathnum'], 1)

            # bug fix on other branch after rename
            self.assertEqual(inducing['file'], 'Main.java')
            self.assertEqual(inducing['adhoc__d2b5b919ce03809c3d07b7f1cd647c6a69fa5c93__2018-01-05 03:01:01+02:00'], 1)
            self.assertEqual(fixing['file'], 'Rubbish.java')
            self.assertEqual(fixing['fix_bug'], True)
            self.assertEqual(fixing['adhoc__d2b5b919ce03809c3d07b7f1cd647c6a69fa5c93__2018-01-05 03:01:01+02:00'], 0)

    def test_date_mixup(self):
        """Tests the case in which a parent has a later date than a child."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/date_mixup.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            # pprint(files)
            # print(files[1]['committer_date'].replace(tzinfo=pytz.UTC)
            self.assertEqual(files[1]['committer_date'].replace(tzinfo=pytz.UTC), datetime.datetime(2018, 1, 3, 3, 1, 1, tzinfo=pytz.UTC))
            self.assertEqual(files[2]['committer_date'].replace(tzinfo=pytz.UTC), datetime.datetime(2018, 1, 2, 3, 1, 1, tzinfo=pytz.UTC))

    def test_rename_bug(self):
        """Test for rename tracking.
        Main.java is inducing an error before beeing renamed to Rubbish.java
        We want to be able to trace the bugfix in Rubbish.java to Main.java.
        """
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/rename.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
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

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            self.assertEqual(files[3]['comm'], 4)  # 4 commits, 2 when named Main.java and 2 after rename to Rubbish.java
            # pprint(files)
