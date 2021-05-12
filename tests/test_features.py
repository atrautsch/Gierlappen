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
from util.config import Config

# usually we want silence in here
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


class TestFeatures(unittest.TestCase):

    def test_kamei_features(self):
        """Test for the additional Kamei  features."""

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

            self.assertEqual(files[0]['kamei_ns'], 2)  # we modify 2 directories which are also subsystems
            self.assertEqual(files[0]['kamei_nd'], 2)
            self.assertEqual(files[0]['kamei_nf'], 2)
            self.assertEqual(files[0]['kamei_entropy'], 1)  # 2 files are added
            self.assertEqual(files[0]['kamei_la'], 10)
            self.assertEqual(files[0]['kamei_ld'], 0)
            self.assertEqual(files[0]['kamei_lt'], -1)  # todo: lt is only for the current commit, however we can not just subtract the added lines because lt does not count empty lines
            self.assertEqual(files[0]['kamei_fix'], False)
            self.assertEqual(files[0]['kamei_ndev'], 1)
            self.assertEqual(files[0]['kamei_age'], 0)  # first commit age is ofc 0
            self.assertEqual(files[0]['kamei_nuc'], 1)  # no previous changes, although we count the current change in every file
            self.assertEqual(files[0]['kamei_exp'], 1)

            self.assertEqual(files[3]['kamei_age'], 1)  # 2 + 0 / 2 days
            self.assertEqual(files[4]['kamei_age'], 397)  # 365 + 31 + 1 / 1 days
            self.assertEqual(files[3]['kamei_ndev'], 2)
            self.assertEqual(files[3]['kamei_entropy'], 0.9182958340544896)
            self.assertEqual(files[4]['kamei_fix'], True)  # bugfix in last change
            self.assertEqual(files[4]['kamei_nuc'], 3)  # package1/Main.java was previously changed in 3 commits
            self.assertEqual(files[4]['kamei_exp'], 2)  # this author authored 2 changes before

    def test_minor_feature(self):
        """Developer counts as minor if his change is less than 5% of the file."""

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/features3.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)

            self.assertEqual(files[1]['minor'], 1)

    def test_complex_jit_features(self):
        """Test the more complex jit features.

            nd = number of modified directories
            entropy = distribution of modified code
            sctr = number of packages modified in commit
            cexp = number of commits on the modified file by the current author
            sexp = number of commits on the subsystem by the current author
            nsctr = number  of packages modified by the author where the current file was modified
            ncomm = number of commits made to files changed with current file
            nsctr = number of packages modified by the author in commits where the current file was changed
            nadev = neighbor
        """

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/features2.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
            #pprint(files)

            self.assertEqual(files[0]['nd'], 2)  # we modify 2 directories in first and second commit
            self.assertEqual(files[0]['sctr'], 2)  #  = number of packages modified in commit this case also 2 packages
            self.assertEqual(files[4]['cexp'], 2)  # 2 times Main.java
            self.assertEqual(files[4]['sexp'], 2)  # package1 and package2 modified
            self.assertEqual(files[2]['oexp'], 0.375)  # second author with this commit contributes this much
            self.assertEqual(files[4]['nsctr'], 2)  # package1/Main.java changes contained one other package change package2/Main.java
            self.assertEqual(files[4]['ncomm'], 0)  # no neighbors in this case, no ncomm
            self.assertEqual(files[3]['ncomm'], 2)  # always 2 files modified

            self.assertEqual(files[0]['rexp'], 1)
            self.assertEqual(files[4]['rexp'], 1)  # last is same file same author as first but one year later
            self.assertEqual(files[4]['exp'], 1.5)  # 2 commits by test, 1 commit by test2 = 3/2=1.5
            self.assertEqual(files[0]['lt'], 4)
            self.assertEqual(files[2]['lt'], 5)

            self.assertEqual(files[0]['add'], 0.5)  # added 5/10 lines
            self.assertEqual(files[2]['del'], 1)  # one line deleted of 1 all deletions

            # self.assertEqual(files[0]['lt'])
            # self.assertEqual(files[0]['la'], 5)  # add 5 lines in first commit and file
            # self.assertEqual(files[1]['la'], 1)
            # self.assertEqual(files[1]['ld'], 1)
            # self.assertEqual(files[1]['file'], 'Main.java')


    def test_basic_jit_features(self):
        """Test basic jit features, lines added, deleted, ownership, authors as well as age."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/features.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            args = Args()
            args.path = tmpdirname
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)
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
            self.assertEqual(files[0]['ddev'], 1)
            self.assertEqual(files[1]['ddev'], 2)

            # age is retained after rename
            # age is the number of days after the last change
            self.assertEqual(files[1]['file'], 'Main.java')
            self.assertEqual(abs(files[1]['committer_date'] - datetime.datetime(2018, 1, 3, 1, 1, 1, tzinfo=pytz.UTC)), datetime.timedelta(seconds=0))

            self.assertEqual(files[3]['file'], 'Rubbish.java')
            self.assertEqual(abs(files[3]['committer_date'] - datetime.datetime(2018, 1, 4, 1, 1, 1, tzinfo=pytz.UTC)), datetime.timedelta(seconds=0))
            self.assertEqual(files[3]['age'], 1)  # 1 day after last change with old name (files[2] was Test.java)

            # main.java later rubbish.java was only modified alone one time
            self.assertEqual(files[4]['nuc'], 2)  # modified once plus renamed alone once
            self.assertEqual(files[5]['nuc'], 0)  # never modified alone
