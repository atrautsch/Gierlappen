"""Basic linter connector, communicate with tracking/traversal and other connectors (PMD, pylint)"""

import logging
import glob

from pygount import SourceAnalysis
from connectors.pmd_db import PMDConnector
from connectors.pylint import PylintConnector


class LinterConnector():

    def __init__(self, args):
        self._input_path = args.path
        self._log = logging.getLogger('jit.linter')
        self._args = args
        self._files = {}
        self._wd_cache = {}

        # todo: reorganize this next
        if self._args.language == 'python':
            self._extension = 'py'
            self._con = PylintConnector(self, args)
        elif self._args.language == 'java':
            self._extension = 'java'
            self._con = PMDConnector(self, args)

        if not self._input_path.endswith('/'):
            self._input_path += '/'


    def extract_lloc(self):
        files = {}  # needs to reset here
        for check in glob.glob('{}/**/*.{}'.format(self._input_path, self._extension), recursive=True):
            source_analysis = SourceAnalysis.from_file(check, "pygount")
            relpath = source_analysis.path.replace(self._input_path, '')

            if relpath.startswith('/'):
                relpath = relpath[1:]

            if relpath not in files.keys():
                files[relpath] = {'warnings': [], 'lloc': source_analysis.code_count, 'warning_list': []}
        return files

    def _get_line_numbers(self, modifications, file_name):
        # find files that only changed in this commit, take the changed lines numbers and compare them with those reported by PMD
        for _, new_path, _, _, _, _, added_line_numbers, deleted_line_numbers in modifications:
            if file_name == new_path:
                return added_line_numbers, deleted_line_numbers
        return {}, {}

    def add_commit(self, global_state, commit):
        """Called from tracking, runs PMD on the commit.

        Also we sadly have to take care of a lot of aggregations here.
        This should be refactored.
        """
        self._current_warnings = self._con.run_linter(commit.hash)
        self._parent_warnings = {}

        if len(commit.parents) > 0:
            self._parent_warnings = self._con.run_linter(commit.parents[0])

        self._parent_system_wd = 0
        self._sum_current_warnings = 0
        self._sum_current_lloc = 0
        self._added_warning_lines = {}
        self._deleted_warning_lines = {}
        self._sum_filtered_warnings = 0
        self._parent_system_default_wd = 0
        self._effective_system_wd = 0  # only effective rules, either emtpy, default rules from maven pmd or custom defined rules
        self._parent_effective_system_wd = 0
        self._sum_effective_warnings = 0
        self._num_files = 0
        for fname, pmdval in self._current_warnings.items():
            if self._args.filename_filter(fname): # we need the full state, all files
                self._sum_current_warnings += len(pmdval['warnings'])
                self._sum_current_lloc += pmdval['lloc']
                self._sum_filtered_warnings += len(self._con.filter_default_warnings(pmdval['warnings']))
                self._num_files += 1
                if hasattr(global_state, '_build'):
                    self._sum_effective_warnings += len(self._con.filter_effective_warnings(pmdval['warnings'], global_state._build.get_file_metrics(fname)))

                added_line_numbers, _ = self._get_line_numbers(global_state.modifications, fname)
                if fname not in self._added_warning_lines.keys():
                    self._added_warning_lines[fname] = []
                for w in pmdval['warning_list']:
                    if int(w['Line']) in added_line_numbers:
                        self._added_warning_lines[fname].append(w['Rule'])

        # now we want the deleted warnings
        for fname, pmdval in self._parent_warnings.items():
            if self._args.filename_filter(fname):

                _, deleted_line_numbers = self._get_line_numbers(global_state.modifications, fname)
                if fname not in self._deleted_warning_lines.keys():
                    self._deleted_warning_lines[fname] = []
                for w in pmdval['warning_list']:
                    if int(w['Line']) in deleted_line_numbers:
                        self._deleted_warning_lines[fname].append(w['Rule'])

        wd = 0
        if self._sum_current_lloc > 0:
            wd = self._sum_current_warnings / self._sum_current_lloc

        self._current_system_wd = wd
        self._current_system_default_wd = 0
        if self._sum_current_lloc > 0:
            self._current_system_default_wd = self._sum_filtered_warnings / self._sum_current_lloc
            self._effective_system_wd = self._sum_effective_warnings / self._sum_current_lloc

        self._wd_cache[commit.hash] = (wd, self._sum_current_warnings, self._current_system_default_wd, self._effective_system_wd)

        if commit.parents:
            self._parent_system_wd = self._wd_cache[commit.parents[0]][0]
            self._parent_warning_sum = self._wd_cache[commit.parents[0]][1]
            self._parent_system_default_wd = self._wd_cache[commit.parents[0]][2]
            self._parent_effective_system_wd = self._wd_cache[commit.parents[0]][3]

        # authors change in warning density, independent of files, we need only the change
        author = global_state.get_author(commit)
        if 'wd' not in global_state.authors[author].keys():
            global_state.authors[author]['wd'] = []
        if 'default_wd' not in global_state.authors[author].keys():
            global_state.authors[author]['default_wd'] = []
        if 'effective_wd' not in global_state.authors[author].keys():
            global_state.authors[author]['effective_wd'] = []

        global_state.authors[author]['wd'].append(self._current_system_wd - self._parent_system_wd)
        if commit.parents:
            global_state.authors[author]['default_wd'].append(self._current_system_default_wd - self._parent_system_default_wd)
            global_state.authors[author]['effective_wd'].append(self._effective_system_wd - self._parent_effective_system_wd)

    def get_file_metrics(self, global_state, author, name, original_name, is_deleted):
        tmp = {'linter_warnings': float('inf'),
               'linter_parent_warnings': 0,
               'linter_lloc': self._sum_current_lloc,  # maybe rename to system_lloc
               'current_WD': 0,
               'current_default_WD': 0,
               'current_system_WD': self._current_system_wd,
               'current_system_default_WD': self._current_system_default_wd,
               'parent_system_default_WD': self._parent_system_default_wd,
               'current_system_warning_sum': self._sum_current_warnings,
               'parent_WD': 0,
               'parent_system_WD': self._parent_system_wd,
               'parent_default_WD': 0,
               'parent_system_warning_sum': 0,
               'linter_added_warnings': [],
               'linter_deleted_warnings': [],
               'linter_warning_list': [],
               'system_WD': self._current_system_wd,
               'delta_system_WD': self._current_system_wd - self._parent_system_wd,
               'delta_system_default_WD': self._current_system_default_wd - self._parent_system_default_wd,
               'effective_system_WD': self._effective_system_wd,
               'parent_effective_system_WD': self._parent_effective_system_wd,
               'delta_effective_system_WD': self._effective_system_wd - self._parent_effective_system_wd,
               'current_effective_WD': 0,
               'linter_files': self._num_files,
               }

        if original_name in self._added_warning_lines.keys():
            tmp['linter_added_warnings'] = self._added_warning_lines[original_name]
        if original_name in self._deleted_warning_lines.keys():
            tmp['linter_deleted_warnings'] = self._deleted_warning_lines[original_name]
        if original_name in self._current_warnings.keys():
            tmp['linter_warnings'] = len(self._current_warnings[original_name]['warnings'])

        if self._parent_system_wd and original_name in self._parent_warnings.keys():
            tmp['linter_parent_warnings'] = len(self._parent_warnings[original_name]['warnings'])

        if is_deleted and original_name in self._current_warnings.keys():
            self._log.error('We found %s but it should be deleted', original_name)

        if original_name in self._current_warnings.keys():
            tmp['linter_warning_list'] = self._current_warnings[original_name]['warnings']
            if self._current_warnings[original_name]['lloc']:
                tmp['current_WD'] = tmp['linter_warnings'] / self._current_warnings[original_name]['lloc']
                tmp['current_default_WD'] = len(self._con.filter_default_warnings(self._current_warnings[original_name]['warnings'])) / self._current_warnings[original_name]['lloc']
                if hasattr(global_state, '_build'):  # this only works if we have the build information about custom rules
                    tmp['current_effective_WD'] = len(self._con.filter_effective_warnings(self._current_warnings[original_name]['warnings'], global_state._build.get_file_metrics(original_name))) / self._current_warnings[original_name]['lloc']

        # no parent for effective and default because we do not have the build information of the parent at hand
        if self._parent_system_wd:
            tmp['parent_system_WD'] = self._parent_system_wd
            tmp['parent_system_warning_sum'] = self._parent_warning_sum
            if original_name in self._parent_warnings.keys() and self._parent_warnings[original_name]['lloc']:
                tmp['parent_WD'] = len(self._parent_warnings[original_name]['warnings']) / self._parent_warnings[original_name]['lloc']
                tmp['parent_default_WD'] = len(self._con.filter_default_warnings(self._parent_warnings[original_name]['warnings'])) / self._parent_warnings[original_name]['lloc']

        if self._current_system_wd:
            # we may have to create these
            if 'wd' not in global_state.files[name].keys():
                global_state.files[name]['wd'] = []
            if 'default_wd' not in global_state.files[name].keys():
                global_state.files[name]['default_wd'] = []
            if 'effective_wd' not in global_state.files[name].keys():
                global_state.files[name]['effective_wd'] = []

            global_state.files[name]['wd'].append(tmp['current_WD'] - self._current_system_wd)
            global_state.files[name]['default_wd'].append(tmp['current_default_WD'] - self._current_system_default_wd)
            global_state.files[name]['effective_wd'].append(tmp['current_effective_WD'] - self._effective_system_wd)

            tmp['file_system_sum_WD'] = sum(global_state.files[name]['wd'])
            tmp['file_system_sum_default_WD'] = sum(global_state.files[name]['default_wd'])
            tmp['decayed_file_system_sum_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.files[name]['wd']))])
            tmp['decayed_file_system_sum_default_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.files[name]['default_wd']))])
            tmp['decayed_file_system_sum_effective_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.files[name]['effective_wd']))])

            tmp['author_delta_sum_WD'] = sum(global_state.authors[author]['wd'])
            tmp['author_delta_sum_default_WD'] = sum(global_state.authors[author]['default_wd'])
            tmp['decayed_author_delta_sum_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.authors[author]['wd']))])
            tmp['decayed_author_delta_sum_default_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.authors[author]['default_wd']))])
            tmp['decayed_author_delta_sum_effective_WD'] = sum([wdv / (pos + 1) for pos, wdv in enumerate(reversed(global_state.authors[author]['effective_wd']))])
        return tmp
