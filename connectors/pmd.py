"""Executes PMD on all files of the passed commit.
Also includes pygounit for lloc count to calculate warning density.
"""

import subprocess
import tempfile
import logging
import csv
import glob
import pickle
import os

from pygount import SourceAnalysis

class PMDConnector():
    """Experimental PMD conector for Gierlappen."""

    def __init__(self, gr, input_path, pmd_path='/srv/www/Gierlappen2/checks/pmd'):
        self._gr = gr
        self._pmd_path = pmd_path
        self._input_path = input_path
        self._log = logging.getLogger('jit.pmd_connector')
        self._cache = {}  # this is the Gierlappen cache
        self._files = {}

        if not input_path.endswith('/'):
            input_path += '/'

        # creates temporary cache file for PMD used by PMD
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            self._cache_file = f.name

    def load_cache(self, cache_file):
        """Load the cache file containing all PMD warnings and LLOC for all revisions and files."""
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                self._cache = pickle.load(f)

    def save_cache(self, cache_file):
        """Save colected data to cache as pickle."""
        with open(cache_file, 'wb') as f:
            pickle.dump(self._cache, f)

    def _extract_lloc(self):
        self._files = {}  # needs to reset here
        for check in glob.glob('{}/**/*.java'.format(self._input_path), recursive=True):
            source_analysis = SourceAnalysis.from_file(check, "pygount")
            relpath = source_analysis.path.replace(self._input_path, '')

            if relpath.startswith('/'):
                relpath = relpath[1:]

            if relpath not in self._files.keys():
                self._files[relpath] = {'warnings': [], 'lloc': source_analysis.code_count, 'warning_list': []}

    def run_pmd(self, commit):
        """Check out the given commit, then run pmd and pygount on all files."""
        if commit.hash in self._cache.keys():
            return self._cache[commit.hash]

        self._gr.repo.git.checkout(commit.hash, '--force')

        cmds = ['{}/bin/run.sh'.format(self._pmd_path), 'pmd', '-d', self._input_path, '-f', 'csv', '-cache', '{}'.format(self._cache_file), '-R', '{}/all_rules.xml'.format(self._pmd_path)]

        r = subprocess.run(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self._input_path)

        if r.returncode != 0 and r.returncode != 4:
            self._log.error('error running pmd %s', (r.stderr.decode('utf-8')))
            return self._files

        reader = csv.DictReader(r.stdout.decode('utf-8').splitlines(), quoting=csv.QUOTE_ALL)

        # extract lloc
        self._extract_lloc()

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

        self._cache[commit.hash] = self._files  # deepcopy?

        return self._files
