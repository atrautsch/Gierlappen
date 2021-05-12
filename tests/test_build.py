"""Tests for PomPom."""
import unittest
import tempfile
import subprocess
import logging
import sys
import os
import lxml

from pprint import pprint
from connectors.build import PomPom, PomPomError

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


class TestPomPom(unittest.TestCase):
    """Test basic PomPom implementation."""

    def test_default_path(self):
        """Tests correct return of default pom.xml path."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/build1.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            path = p.get_main_poms()

            self.assertTrue(len(path) == 1)
            self.assertEqual(path.pop(), '/pom.xml')

    def test_non_default_path(self):
        """Test non default path."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build3.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            path = p.get_main_poms()

            self.assertTrue(len(path) == 1)
            self.assertEqual(path.pop(), '/main/pom.xml')

    def test_modules(self):
        """Test submodules."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build2.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            xml = p._parse(tmpdirname + '/pom.xml')
            modules = p._get_modules(xml)

            wants = ['package3', 'package1']
            self.assertEqual(modules, wants)

    def test_default_path_submodules(self):
        """Test submodules."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build2.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            path = p.get_main_poms()

            self.assertTrue(len(path) == 1)
            self.assertEqual(path.pop(), '/pom.xml')

    def test_pom_parse_error(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build_parse_error.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            self.assertRaises(lxml.etree.XMLSyntaxError, p.get_main_poms)

    def test_custom_rule_parse_error(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build_custom_rule_parse_error.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            poms = p.get_main_poms()
            output, replacements = p.create_effective_pom(tmpdirname + poms.pop())

            with self.assertRaises(lxml.etree.XMLSyntaxError):
                p.parse_effective_pom(output)

    def test_custom_rule_parsing(self):
        """Test parsing custom rules."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build_custom_rule_parsing.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            poms = p.get_main_poms()
            output, _ = p.create_effective_pom(tmpdirname + poms.pop())
            pom = p.parse_effective_pom(output)

            main = 'local.test.{}:main-1.0'.format(dirname)

            # basic is expanded
            self.assertTrue('CheckResultSet' in pom[main]['rules'])

            # DuplicateImport is excluded, others are in
            self.assertFalse('DuplicateImport' in pom[main]['rules'])
            self.assertTrue('DontImportJavaLang' in pom[main]['rules'])

    def test_missing_parent(self):
        """Test missing parent exception."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build_missing_parent.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            poms = p.get_main_poms()
            with self.assertRaises(PomPomError) as e:
                _, _ = p.create_effective_pom(tmpdirname + poms.pop())
            self.assertEqual(e.exception.type, 'parent')

    @unittest.skip("skipping because this actually fetches commons-parent from maven central")
    def test_replacing_parent(self):
        """Test replacements for fetching parents from Maven central."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build_replacing_parent.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            poms = p.get_main_poms()
            _, replacements = p.create_effective_pom(tmpdirname + poms.pop())

            self.assertEqual(replacements[0], {'old': 'commons', 'new': 'commons-parent'})

    def test_effective_pom(self):
        """Test building effective pom with idents."""
        with tempfile.TemporaryDirectory() as tmpdirname:
            dirname = os.path.split(os.path.basename(tmpdirname))[-1]
            r = subprocess.run(['/bin/bash', './tests/scripts/build2.sh', '{}'.format(tmpdirname), dirname], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            p = PomPom(tmpdirname)
            path = p.get_main_poms()

            output, replacements = p.create_effective_pom(tmpdirname + path.pop())
            self.assertEqual(replacements, [])
            poms = p.parse_effective_pom(output)

            main_ident = 'local.test.{0}:{0}-1.0'.format(dirname)
            pmd_ident = 'local.test.{}:package3-1.0-SNAPSHOT'.format(dirname)
            p1_ident = 'local.test.{}:package1-1.0-SNAPSHOT'.format(dirname)

            # print(poms)
            self.assertTrue(main_ident in poms)
            self.assertTrue(pmd_ident in poms)
            self.assertTrue(p1_ident in poms)

            self.assertTrue(poms[pmd_ident]['use_pmd'])
            self.assertEqual(poms[main_ident]['source_directory'], 'src/main/java')
            self.assertEqual(poms[main_ident]['test_source_directory'], 'src/test/java')
            self.assertEqual(poms[pmd_ident]['custom_rule_files'], {'{}/package3/pmd-ruleset.xml'.format(tmpdirname)})
