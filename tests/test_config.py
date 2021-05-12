import unittest
import datetime
import os

from util.config import Config


class Args():
    """Default config object we use for these tests."""
    language = 'python'
    connector = None
    production_only = False
    use_maven = False
    quality_keywords = []
    project = 'tmp'
    file_check = True
    is_test = True
    keywords = ['fix']
    to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)
    pmd_path = os.path.abspath('./checks/pmd/')
    path = '/tmp/'
    use_linter = False


class ConfigTest(unittest.TestCase):

    def test_config(self):
        args = Args()

        b = Config(args)

        self.assertEqual(b.language, 'python')
        self.assertEqual(b.extensions, ['.py'])
