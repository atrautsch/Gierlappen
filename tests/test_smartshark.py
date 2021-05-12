#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import json
import importlib
import unittest
import datetime
import subprocess
import tempfile
import logging
import sys

from pprint import pprint
import mongoengine
from bson.objectid import ObjectId

from pycoshark.mongomodels import VCSSystem, Commit, CodeEntityState, File, FileAction, Issue

from connectors.smartshark import SmartSharkConnector
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
    connector = None
    language = 'java'
    production_only = False
    use_linter = False
    use_maven = False
    quality_keywords = {}
    project = 'tmp'
    file_check = True
    is_test = True
    keywords = ['fix']
    extensions = ['.java']
    to_date = datetime.datetime(2020, 12, 31, 23, 59, 59)


class TestSmartshark(unittest.TestCase):
    """Test integration via the smartshark DB.
    This creates a mongomock in-memory database which is fed by json fixtures to set the database to a predefined state.
    """

    def setUp(self):
        """Setup the mongomock connection."""
        mongoengine.connection.disconnect()
        mongoengine.connect('testdb', host='mongomock://localhost')

    def tearDown(self):
        """Tear down the mongomock connection."""
        mongoengine.connection.disconnect()

    def _load_fixture(self, fixture_name):

        # this would be nice but it does not work
        # db = _get_db()
        # db.connection.drop_database('testdb')

        self._ids = {}
        replace_later = {}

        # we really have to iterate over collections
        for col in ['People', 'Project', 'VCSSystem', 'File', 'Commit', 'FileAction', 'CodeEntityState', 'Hunk', 'Issue', 'IssueSystem', 'Identity']:
            module = importlib.import_module('pycoshark.mongomodels')
            obj = getattr(module, col)
            obj.drop_collection()

        with open('tests/fixtures/{}.json'.format(fixture_name), 'r') as f:
            fixture = json.load(f)
            for col in fixture['collections']:

                module = importlib.import_module('pycoshark.mongomodels')
                obj = getattr(module, col['model'])

                for document in col['documents']:
                    tosave = document.copy()
                    had_id_mapping = False

                    for k, v in document.items():
                        if k == 'id':
                            self._ids[document['id']] = None
                            del tosave['id']
                            had_id_mapping = True
                        if type(v) not in [int, list, dict] and v.startswith('{') and v.endswith('}'):
                            tosave[k] = self._ids[v.replace('{', '').replace('}', '')]

                        if type(v) == list:
                            for sv in v:
                                if type(sv) == str and sv.startswith('{') and sv.endswith('}'):
                                    val = sv.replace('{', '').replace('}', '')
                                    if val not in self._ids.keys():
                                        replace_later[col['model']] = {'field': k, 'value': val}
                                    else:
                                        if type(tosave[k]) == list:
                                            tosave[k][tosave[k].index('{' + val + '}')] = self._ids[val]

                    r = obj(**tosave)
                    r.save()
                    if had_id_mapping:
                        self._ids[document['id']] = r.id

    def test_static_metrics(self):
        """Utilize the rename_tracking fixture to check if bug-fixes get assigned to the correct file after subsequent renames."""

        # prepare database
        self._load_fixture('dambros_metrics')

        f1 = File.objects.get(path='package1/Main.java')
        f2 = File.objects.get(path='package2/Main.java')

        bugfix_commit = Commit.objects.get(revision_hash='01b08853519983cd55fee85daff4ec0723f154e0')
        inducing_commit = Commit.objects.get(revision_hash="0d15e8da21d4c3c36fc84a8991070cc3e1e8591e")

        inducing_fa = FileAction.objects.get(commit_id=inducing_commit.id, file_id=f1.id)
        bugfix_fa = FileAction.objects.get(commit_id=bugfix_commit.id, file_id=f1.id)

        inducing_fa.induces = [{"change_file_action_id": bugfix_fa.id, "label": "JLMIV+R", "szz_type": "inducing"},{"change_file_action_id": bugfix_fa.id, "label": "JL+R", "szz_type": "inducing"}]
        inducing_fa.save()

        ces1 = CodeEntityState.objects.get(s_key="CESCOMMIT1FILEA")
        ces2 = CodeEntityState.objects.get(s_key="CESCOMMIT2FILEA")

        # additional classes for file to see if aggregating works
        ces3 = CodeEntityState.objects.get(s_key='CESCOMMIT2CLASS1')
        ces4 = CodeEntityState.objects.get(s_key='CESCOMMIT2CLASS2')
        parent = Commit.objects.get(revision_hash=inducing_commit.parents[0])
        inducing_commit.code_entity_states = [ces2.id, ces3.id, ces4.id]
        inducing_commit.save()

        parent.code_entity_states = [ces1.id]
        parent.save()

        with tempfile.TemporaryDirectory() as tmpdirname:
            r = subprocess.run(['/bin/bash', './tests/scripts/smartshark1.sh', '{}'.format(tmpdirname)], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)

            sms = SmartSharkConnector('Testproject', tmpdirname, True, 'JL+R,JLMIV+R', 'localhost', 27017, 'smartshark', 'guest', 'guest', 'smartshark', is_test=True)

            args = Args()
            args.path = tmpdirname
            args.project = 'Testproject'
            args.connector = sms
            c = Config(args)

            t = Traversal(c)
            ts = t.create_graph()
            files = t.traverse(ts)

            cleared = []
            for instance in files:
                tmp = {}
                for k, v in instance.items():
                    if k.startswith(('current_', 'parent_', 'delta_')):
                        continue
                    tmp[k] = v
                cleared.append(tmp)
            #pprint(cleared)

            # check if we found the correct file as inducing for both labels
            self.assertEqual(cleared[2]['file'], 'package1/Main.java')
            self.assertEqual(cleared[2]['JL+R__TESTPROJECT-1__01b08853519983cd55fee85daff4ec0723f154e0__2018-01-31 23:01:01'], 1)
            self.assertEqual(cleared[2]['JLMIV+R__TESTPROJECT-1__01b08853519983cd55fee85daff4ec0723f154e0__2018-01-31 23:01:01'], 1)

            #pprint(cleared[2])
            # print(files[2]['current_LLOC_file'])
            # check static file metrics and PMD warnings
            self.assertEqual(files[2]['parent_LLOC_file'], 4)
            self.assertEqual(files[2]['current_LLOC_file'], 5)
            self.assertEqual(files[2]['delta_LLOC_file'], 1)
            self.assertEqual(files[2]['parent_PMD_AAA'], 1)
            self.assertEqual(files[2]['current_PMD_AAA'], 2)
            self.assertEqual(files[2]['delta_PMD_AAA'], 1)

            self.assertEqual(files[2]['current_WMC_class_sum'], 60)
            self.assertEqual(files[2]['current_DIT_class_sum'], 28)
