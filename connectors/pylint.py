"""Executes pylingt on all files of the passed commit.
Also includes pygounit for lloc count to calculate warning density.

TODO: - lots of duplicate code betweenn pmd and pylint connectors,
we maybe have to split again for metrics (metric adapters?)
"""

import subprocess
import logging
import json

from adapters.sqlite import SQLiteDatabaseAdapter


class PylintConnector():
    """Experimental PyLint connector for Gierlappen."""

    def __init__(self, con, args):
        self._input_path = args.path
        self._log = logging.getLogger('jit.linter.pylint')
        self._args = args
        self._files = {}
        self._wd_cache = {}
        self._con = con  # connection to the linter connector

        if not self._input_path.endswith('/'):
            self._input_path += '/'

        # connect to db (should be values from config object)
        self._db = SQLiteDatabaseAdapter(args)

    def filter_effective_warnings(self, warnings, custom_rules_data):
        """We skip this for now."""
        return warnings

    def filter_default_warnings(self, warnings):
        """We skip this for now"""
        return warnings

    def run_linter(self, commit_hash):
        """Execute the linter, report back the results"""
        data = self._db.get_commit(commit_hash)
        if data:
            return data

        cmds = ['pylint', '-s', 'n', '-f', 'json', './**/*.py']
        self._log.debug('running linter pylint in %s', self._input_path)
        r = subprocess.run(' '.join(cmds), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self._input_path)

        # https://docs.pylint.org/en/1.6.0/run.html
        if r.returncode == 32:
            self._log.error(' '.join(cmds))
            self._log.error('error running pylint: %s, exit code: %s, stdout: %s', r.stderr.decode('utf-8'), r.returncode, r.stdout.decode('utf-8'))
            return self._files

        warnings = json.loads(r.stdout.decode('utf-8'))

        self._files = self._con.extract_lloc()

        for w in warnings:

            if w['path'] not in self._files.keys():  # this is critical, we are missing something
                raise Exception('{} not in {}'.format(w['path'], self._files.keys()))

            # for consistency with PMD we simple add some aliases into the json
            w['Rule'] = w['message-id']
            w['Line'] = w['line']
            self._files[w['path']]['warnings'].append(w['message-id'])
            self._files[w['path']]['warning_list'].append(w)

        self._db.save_commit(commit_hash, self._files)

        return self._files
