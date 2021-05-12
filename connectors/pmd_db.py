"""Executes PMD on all files of the passed commit.
Also includes pygounit for lloc count to calculate warning density.

We use a postgresql connector here because otherwise the data would
get too much (commons-validator has a 2.3GB pickle).
"""

import subprocess
import tempfile
import logging
import csv
import glob

from pygount import SourceAnalysis

from pycoshark.utils import java_filename_filter

from adapters.sqlite import SQLiteDatabaseAdapter
#from adapters.postgres import PostgresDatabaseAdapter
from const import MVN_DEFAULT


class PMDConnector():
    """Experimental PMD connector for Gierlappen."""

    def __init__(self, con, args):
        self._pmd_path = args.pmd_path
        self._input_path = args.path
        self._log = logging.getLogger('jit.linter.pmd')
        self._args = args
        self._con = con
        self._files = {}

        if not self._input_path.endswith('/'):
            self._input_path += '/'

        # creates temporary cache file for PMD used by PMD
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            self._cache_file = f.name

        # SQLITE = DEFAULT, also for tests
        self._db = SQLiteDatabaseAdapter(args)

        # if we have pg_sql username we connect
        #if args.pg_user:
        #    self._db = PostgresDatabaseAdapter(args)

    def filter_default_warnings(self, warnings):
        """Return only maven pmd plugin default warnings."""
        filtered = []
        for w in warnings:
            if w in MVN_DEFAULT:
                filtered.append(w)
        return filtered

    def filter_effective_warnings(self, warnings, custom_rules_data):
        """Return only maven pmd plugin default warnings."""
        filtered = []
        if not custom_rules_data['use_pmd']:
            return filtered

        custom_rules = custom_rules_data['custom_rules']
        for w in warnings:
            if w in custom_rules:
                filtered.append(w)
        return filtered

    def run_linter(self, commit_hash):
        """Check out the given commit, then run pmd and pygount on all files."""
        data = self._db.get_commit(commit_hash)
        if data:
            return data

        cmds = ['{}/bin/run.sh'.format(self._pmd_path), 'pmd', '-d', self._input_path, '-f', 'csv', '-cache', '{}'.format(self._cache_file), '-R', '{}/all_rules.xml'.format(self._pmd_path)]

        r = subprocess.run(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self._input_path)

        if r.returncode != 0 and r.returncode != 4:
            self._log.error('error running pmd %s', (r.stderr.decode('utf-8')))
            return self._files

        reader = csv.DictReader(r.stdout.decode('utf-8').splitlines(), quoting=csv.QUOTE_ALL)

        # extract lloc
        self._files = self._con.extract_lloc()

        for line in reader:
            relpath = line['File'].replace(self._input_path, '')
            if relpath.startswith('/'):
                relpath = relpath[1:]

            if relpath not in self._files.keys():  # this is critical, we are missing something
                raise Exception('{} not in {}'.format(relpath, self._files.keys()))

            # files has to exist because of lloc
            self._files[relpath]['warnings'].append(line['Rule'])
            self._files[relpath]['warning_list'].append(line)
            # self._log.debug('found PMD warning %s on %s', line['Rule'], relpath)
            # self._log.debug('rule: %s, problem: %s', line['Rule'], line['Problem'])
            # self._log.debug('keys %s', line.keys())

        # self._cache[commit.hash] = self._files  # deepcopy?
        self._db.save_commit(commit_hash, self._files)

        return self._files
