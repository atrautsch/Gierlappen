"""Track files and hold state. State includes all metrics for files and authors."""

import copy
import logging

import numpy as np
from pydriller.domain.commit import ModificationType


class PathState:
    """PathState holds the current state of the path.

    If the file is renamed due to a move we also rename it in our state.
    """

    def __init__(self, files=None):
        self.files = {}
        if files:
            self.files = files

    def add_file(self, name):
        if name in self.files.keys():
            raise Exception('File {} already existing!'.format(name))
        self.files[name] = {'commits': 1}

    def del_file(self, name):
        if name not in self.files.keys():
            raise Exception('File {} does not exist!'.format(name))
        del self.files[name]

    def modify_file(self, name):
        if name not in self.files.keys():
            print(self.files.keys())
            raise Exception('File {} does not exist!'.format(name))
        self.files[name]['commits'] += 1

    def move_file(self, old_name, new_name):
        if old_name not in self.files.keys():
            raise Exception('Move: {0}->{1} {0} does not exist'.format(old_name, new_name))
        if new_name in self.files.keys():
            raise Exception('Move: {0}->{1} {1} already existing'.format(old_name, new_name))
        self.files[new_name] = copy.deepcopy(self.files[old_name])
        del self.files[old_name]


class GlobalState:
    """GobalState holds the global state over every path.

    We accumulate data for each file and calculate features from the accumulated data.
    """

    def __init__(self, config):
        self._config = config
        self.files = {}
        self.aliases = {}
        self.authors = {}
        self.commits = {}  # commit level features are collected here
        self._project_path = config.path
        self._quality_keywords = config.quality_keywords
        self._bug_keywords = config.keywords
        self.quality = {}
        self.production_only = config.production_only
        self._build_information = {}
        self._sm_con = False
        self._pmd_con = False
        self._build_con = False
        self._wd_cache = {}

        self.metrics = []

        self._its_inducing = {}
        self._adhoc_inducing = {}
        self._inducing_commits = set()
        self._inducing_files = set()

        self._log = logging.getLogger('jit.gstate')

    def __setstate__(self, state):
        """We need to re-set the _pmd_con"""
        self.__dict__ = state
        self._pmd_con = False

    def __getstate__(self):
        """We exclude possible sqlite database connections here from pickling to the state file.
        This needs some more work. Some of this information is saved in more places,
        e.g., project_path already in Config.
        """
        state = self.__dict__.copy()
        del state['_pmd_con']
        return state

    def get_author(self, commit):
        return commit.author.email

    def get_subsystem(self, filepath):
        return '/'.join(filepath.split('/')[:-1])

    def set_its_inducing(self, label, inducings):
        self._its_inducing[label] = inducings

    def set_inducing_files(self, inducing_files):
        self._inducing_files = inducing_files

    def set_adhoc_inducing(self, inducings):
        self._adhoc_inducing = inducings

    def set_inducing_commits(self, inducing_commits):
        self._inducing_commits = inducing_commits

    def set_linter_connector(self, pmd_con):
        self._pmd_con = pmd_con

    def set_build_connector(self, build_con):
        self._build_con = build_con

    def set_smartshark_connector(self, sm_con):
        self._sm_con = sm_con

    def add_author(self, commit):
        author = self.get_author(commit)

        if author not in self.authors.keys():
            self.authors[author] = {'subsystems': {}, 'changes': [], 'years': {}, 'files': {}, 'lines': 0, 'nsctr': {}, 'wd': [], 'commits': set()}

        self.authors[author]['changes'].append(commit.committer_date)
        self.authors[author]['commits'].add(commit.hash)

        year = commit.committer_date.year
        if year not in self.authors[author]['years']:
            self.authors[author]['years'][year] = 0
        self.authors[author]['years'][year] += 1

    def add_commit(self, commit):

        # add author related stuff
        self.add_author(commit)

        # reset metrics
        self.metrics = []

        # create real modification list, this may be different to the one provided by pydriller
        self.modifications = []
        hunks = {}
        for mod in commit.modifications:
            if mod.change_type is not ModificationType.RENAME:
                if mod.new_path and not self._config.filename_filter(mod.new_path):
                    continue
                if mod.old_path and not self._config.filename_filter(mod.old_path):
                    continue

            added_line_numbers = [lno for lno, ls in mod.diff_parsed['added']]
            deleted_line_numbers = [lno for lno, ls in mod.diff_parsed['deleted']]

            if mod.change_type is ModificationType.RENAME:
                if not self._config.filename_filter(mod.new_path) and self._config.filename_filter(mod.old_path):
                    self.modifications.append((ModificationType.DELETE, mod.new_path, mod.old_path, mod.added, mod.removed, mod.nloc, added_line_numbers, deleted_line_numbers))
                if not self._config.filename_filter(mod.old_path) and self._config.filename_filter(mod.new_path):
                    self.modifications.append((ModificationType.ADD, mod.new_path, mod.old_path, mod.added, mod.removed, mod.nloc, added_line_numbers, deleted_line_numbers))
                if self._config.filename_filter(mod.old_path) and self._config.filename_filter(mod.new_path):
                    self.modifications.append((mod.change_type, mod.new_path, mod.old_path, mod.added, mod.removed, mod.nloc, added_line_numbers, deleted_line_numbers))
            else:
                self.modifications.append((mod.change_type, mod.new_path, mod.old_path, mod.added, mod.removed, mod.nloc, added_line_numbers, deleted_line_numbers))

        # try to find missing renames
        adds = []
        dels = []
        for m in commit.modifications:
            if m.change_type == ModificationType.ADD:
                adds.append(m.new_path)
            elif m.change_type == ModificationType.DELETE:
                dels.append(m.old_path)
        for a in adds:
            for d in dels:
                if a.split('/')[-1] == d.split('/')[-1]:
                    self._log.debug('[%s] possible rename: %s -> %s', commit.hash, d, a)

        # build stuff, needs commit
        if self._build_con:
            self._build_con.add_commit(commit)

        # smartshark metrics if available
        # self.smartshark_labels = its_inducings
        # self.current_system_wd = 0
        # if self._sm_con and not self._pmd_con:
            # # self._log.debug('[%s] getting warning density', commit.hash)
            # self.current_system_wd = self._sm_con.get_warning_density(str(commit.hash))

        # self.parent_system_wd = 0
        # if commit.parents and self._sm_con and not self._pmd_con:
            # self.parent_system_wd = self._sm_con.get_warning_density(commit.parents[0])

        # the dream: offload the hideous calculations to the pmd connector
        if self._pmd_con:
            self._pmd_con.add_commit(self, commit)

        # add quality keywords if available
        if self._quality_keywords:
            for topic in self._quality_keywords.keys():
                self.quality[topic] = False

            lines = ''
            for line in commit.msg.lower().split('\n'):
                if line.startswith('git-svn-id'):
                    continue
                if line.lower().startswith('signed-off'):
                    continue
                if not line:
                    continue
                lines += line + ' '

            for quality_topic, keywords in self._quality_keywords.items():
                if any(keyword in lines.split() for keyword in keywords):
                    self.quality[quality_topic] = True

    def get_modified_lines(self, commit):
        files = []
        for m in commit.modifications:
            files.append(m.added + m.removed)
        return files

    def get_modified_subsystems(self, commit):
        subsystems = set()
        for mod in commit.modifications:
            name = mod.new_path
            if mod.change_type is ModificationType.DELETE:
                name = mod.old_path
            subsystems.add(self.get_subsystem(name))
        return subsystems

    def get_modified_directories(self, commit):
        directories = set()
        for mod in commit.modifications:
            name = mod.new_path
            if mod.change_type is ModificationType.DELETE:
                name = mod.old_path
            try:
                directory = name.split('/')[-2]
            except IndexError:
                directory = '/'
            directories.add(directory)
        return directories

    def calculate_metrics(self, commit):
        current_year = commit.committer_date.year
        author = self.get_author(commit)
        subsystems = self.get_modified_subsystems(commit)
        directories = self.get_modified_directories(commit)
        lines = self.get_modified_lines(commit)
        all_added = sum([m.added for m in commit.modifications])
        all_removed = sum([m.removed for m in commit.modifications])
        all_loc = sum([m.nloc for m in commit.modifications if m.nloc is not None])
        is_bugfix = any(word in commit.msg.lower() for word in self._bug_keywords)

        ctmp = {'kamei_ns': len(subsystems),
                'kamei_nd': len(directories),
                'kamei_nf': len(commit.modifications),
                'kamei_entropy': 0,
                'kamei_la': all_added,
                'kamei_ld': all_removed,
                'kamei_lt': all_loc + all_removed - all_added,
                'kamei_fix': is_bugfix,
                'kamei_ndev': set(),
                'kamei_age': [],
                'kamei_nuc': set(),
                'kamei_exp': len(self.authors[author]['commits']),
                'kamei_sexp': 0,
                'kamei_rexp': 0}
        all_lines = sum(lines)

        if all_lines > 0:
            ctmp['kamei_entropy'] = -sum([line/all_lines * np.log2(line/all_lines) for line in lines if line > 0])

        # this is duplicated for simplicity in this awful code
        for change_type, new_path, old_path, added, removed, nloc, _, _ in self.modifications:

            original_name = new_path
            if change_type is ModificationType.DELETE:
                original_name = old_path

            if not self._config.filename_filter(original_name):
                continue

            name = self.aliases[original_name]
            subsystem = self.get_subsystem(original_name)

            # commit-level jit also needs some history metrics
            ctmp['kamei_ndev'].update(self.files[name]['authors'].keys())
            last_change = 0
            if len(self.files[name]['dates']) > 1:
                last_change = (commit.committer_date - self.files[name]['dates'][-2]).days
            ctmp['kamei_age'].append(last_change)
            ctmp['kamei_nuc'].update(set(self.files[name]['commits']))
            for year, changes in self.authors[author]['years'].items():
                if year <= commit.committer_date.year:
                    ctmp['kamei_rexp'] += changes / (commit.committer_date.year - year + 1)
                else:
                    ctmp['kamei_rexp'] += changes / (year - commit.committer_date.year + 1)  # this can happen if some commits have a different date than parent or the author worked on another branch

            if subsystem in self.authors[author]['subsystems'].keys():
                ctmp['kamei_sexp'] += len(set(self.authors[author]['subsystems'][subsystem]))

        ctmp['kamei_ndev'] = len(ctmp['kamei_ndev'])
        if len(ctmp['kamei_age']) > 0:
            ctmp['kamei_age'] = np.mean(ctmp['kamei_age'])
        ctmp['kamei_nuc'] = len(ctmp['kamei_nuc'])

        # fine grained jit
        for change_type, new_path, old_path, added, removed, nloc, _, _ in self.modifications:

            original_name = new_path
            if change_type is ModificationType.DELETE:
                original_name = old_path

            name = self.aliases[original_name]
            subsystem = self.get_subsystem(original_name)

            tmp = {'commit': commit.hash, 'committer_date': commit.committer_date, 'file': original_name, 'oldest_name': name,'change_type': str(change_type)}
            tmp['comm'] = len(self.files[name]['commits'])
            tmp['adev'] = len(self.files[name]['authors'].keys())
            tmp['ddev'] = len(set(self.files[name]['authors'].keys()))
            tmp['add'] = 0
            tmp['del'] = 0

            if all_added > 0:
                tmp['add'] = added / all_added
            if all_removed > 0:
                tmp['del'] = removed / all_removed

            try:
                tmp['own'] = author == max(self.files[name]['authors'], key=self.files[name]['authors'].get)  # get max key by its value from authors dict
            except ValueError:  # max argument empty
                tmp['own'] = True

            tmp['minor'] = 0
            all_changes = sum(self.files[name]['authors'].values())
            for _, contributed in self.files[name]['authors'].items():
                if contributed < (0.05 * all_changes):
                    tmp['minor'] += 1

            tmp['sctr'] = len(subsystems)
            tmp['nd'] = len(directories)

            entropy = lines
            tmp['entropy'] = 0
            if sum(entropy) > 0:
                tmp['entropy'] = -sum([a / sum(entropy) * np.log2(a / sum(entropy)) for a in entropy if a > 0])
            if np.isnan(tmp['entropy']):
                tmp['entropy'] = 0

            tmp['la'] = added
            tmp['ld'] = removed

            tmp['cexp'] = 0
            if name in self.authors[author]['files'].keys():
                tmp['cexp'] = self.authors[author]['files'][name]

            tmp['rexp'] = 0
            if current_year in self.authors[author]['years'].keys():
                tmp['rexp'] = self.authors[author]['years'][current_year]

            tmp['sexp'] = 0
            if subsystem in self.authors[author]['subsystems'].keys():
                tmp['sexp'] = len(self.authors[author]['subsystems'][subsystem])

            tmp['nuc'] = self.files[name]['unique_changes']

            tmp['age'] = 0
            if len(self.files[name]['dates']) > 1:
                tmp['age'] = (commit.committer_date - self.files[name]['dates'][-2]).days

            # percentage of lines authored by current author in the whole project
            tmp['oexp'] = 0
            if sum([v['lines'] for v in self.authors.values()]) > 0:
                tmp['oexp'] = self.authors[author]['lines'] / sum([v['lines'] for v in self.authors.values()])

            #  mean of experience of all authors in the whole project (exp = number of commits)
            tmp['exp'] = sum([len(v['changes']) for v in self.authors.values()]) / len(self.authors.keys())

            # number of different packages the author changed in all commits which also changed this file
            # - get all changesets where this file was changed by this developer, count the unique packages
            tmp['nsctr'] = 0
            if name in self.authors[author]['nsctr'].keys():
                tmp['nsctr'] = len(self.authors[author]['nsctr'][name])

            # number of commits made to files involved in commits where the file has been modified
            tmp['ncomm'] = set()
            tmp['nadev'] = []
            tmp['nddev'] = set()
            for m in commit.modifications:
                neighbor = m.new_path
                if m.change_type is ModificationType.DELETE:
                    neighbor = m.old_path

                if not self._config.filename_filter(neighbor):
                    continue

                if neighbor == original_name:
                    continue

                neighbor = self.aliases[neighbor]
                if neighbor in self.files.keys():
                    tmp['ncomm'].update(tuple(self.files[neighbor]['commits']))
                    tmp['nadev'] += list(self.files[neighbor]['authors'].keys())
                    tmp['nddev'].update(tuple(self.files[neighbor]['authors'].keys()))

            tmp['ncomm'] = len(tmp['ncomm'])
            tmp['nadev'] = len(tmp['nadev'])
            tmp['nddev'] = len(tmp['nddev'])
            tmp['lt'] = nloc

            # add smartshark features
            parent = None
            if commit.parents:
                parent = commit.parents[0]

            # if we have the smartshark connector we update our features accordingly
            if self._sm_con:
                tmp['validated_bugfix'] = False
                # TODO: this throws errors if we do not yet have the commit, make sure we are in our date range
                if commit.committer_date <= self._config.to_date.replace(tzinfo=commit.committer_date.tzinfo):
                    self._log.debug('committer date %s <= to_date %s', commit.committer_date, self._config.to_date)
                    # We skip all metrics if we do not have the smartshark data, otherwise we would have missing features
                    try:
                        tmp.update(**self._sm_con.get_static_features(original_name, commit.hash, parent))
                        self._log.warning('commit %s not ins smartshark database, skipping', commit.hash)
                    except:
                        return
                    needle = '{}__{}'.format(commit.hash, original_name)
                    if needle in self._sm_con.bugfixes:
                        tmp['validated_bugfix'] = True

            # pmd stuff
            if self._pmd_con:
                pmd = self._pmd_con.get_file_metrics(self, author, name, original_name, change_type == ModificationType.DELETE)
                tmp.update(**pmd)

            tmp['previous_inducing'] = self.files[name]['previous_inducing']

            # add labels
            tmp['fix_bug'] = is_bugfix

            k = '{}__{}'.format(commit.hash, original_name)
            tmp['label_adhoc'] = self._adhoc_inducing.get(k, [])

            for label, inducing in self._its_inducing.items():
                tmp['label_{}'.format(label)] = inducing.get(k, [])
            # only for comparison with pascarella
            tmp['pascarella_commit'] = commit.hash in self._inducing_commits
            tmp['pascarella_file'] = '{}$${}'.format(commit.hash, original_name) in self._inducing_files

            # lets see how this works, we count inducing changes for each file
            if tmp['label_adhoc']:
                self.files[name]['previous_inducing'] += 1

            # quality kwywords
            for topic in self._quality_keywords.keys():

                # file aggregation
                tmp['quality_{}'.format(topic)] = self.files[name]['quality_topics'][topic]

                # only commit, no aggregation
                tmp['quality_{}_commit'.format(topic)] = self.quality[topic]

            tmp.update(**ctmp)

            # add build information to metrics
            if self._build_con:
                btmp = self._build_con.get_file_metrics(original_name)
                tmp.update(**btmp)

            self.metrics.append(tmp)

    def add_file_state(self, name, original_name, commit, mod):
        subsystem = self.get_subsystem(original_name)
        author = self.get_author(commit)
        subsystems = self.get_modified_subsystems(commit)
        self.authors[author]['lines'] += mod.added + mod.removed
        if name not in self.authors[author]['files']:
            self.authors[author]['files'][name] = 0
        self.authors[author]['files'][name] += 1

        if subsystem not in self.authors[author]['subsystems'].keys():
            self.authors[author]['subsystems'][subsystem] = set()
        self.authors[author]['subsystems'][subsystem].add(commit.hash)

        if name not in self.authors[author]['nsctr']:
            self.authors[author]['nsctr'][name] = set()
        self.authors[author]['nsctr'][name].update(subsystems)

        # file stuff
        if len(commit.modifications) == 1:
            self.files[name]['unique_changes'] += 1

        if author not in self.files[name]['authors'].keys():
            self.files[name]['authors'][author] = 0
        self.files[name]['authors'][author] += mod.added + mod.removed

        self.files[name]['commits'].append(commit.hash)
        self.files[name]['dates'].append(commit.committer_date)

        # add quality factors
        for topic, value in self.quality.items():
            if value:
                self.files[name]['quality_topics'][topic] += 1

    def add_file(self, name, commit, mod):
        if name in self.aliases.keys():
            al = self.aliases[name]
        else:
            self.aliases[name] = name
            al = name

        if al not in self.files.keys():
            self.files[al] = {'commits': [], 'dates': [], 'authors': {}, 'unique_changes': 0, 'wd': [], 'previous_inducing': 0}

            # if we have quality keywords we also initialize them for each new file
            if self._quality_keywords:
                self.files[al]['quality_topics'] = {}
                for topic in self._quality_keywords.keys():
                    self.files[al]['quality_topics'][topic] = 0

        # author stuff
        self.add_file_state(al, name, commit, mod)

    def del_file(self, name, commit, mod):
        # author stuff
        self.add_file_state(self.aliases[name], name, commit, mod)

    def modify_file(self, name, commit, mod):
        if name not in self.aliases.keys():
            raise Exception('File {} does not exist in aliases!'.format(name))
        if self.aliases[name] in self.files.keys():
            # self.files[self.aliases[name]]['commits'] += 1
            pass

        # author stuff
        self.add_file_state(self.aliases[name], name, commit, mod)

    def move_file(self, old_name, new_name, commit, mod):
        # this is normal as another path may have moved all files already
        # if old_name in self.aliases.keys():
        #    self._log.warning('Move {}->{} {} in aliases'.format(old_name, new_name, old_name))

        warn = False
        if new_name in self.aliases.keys() and self.aliases[new_name] != old_name:
            self._log.warning('Move %s->%s Missmatch: %s!=%s in aliases', old_name, new_name, self.aliases[new_name], old_name)
            warn = True
        # follow old aliases to the oldest name to get the file reference
        while old_name in self.aliases.keys() and self.aliases[old_name] != old_name:
            old_name = self.aliases[old_name]

        self.aliases[new_name] = old_name

        if warn:
            self._log.warning('Move final is now %s -> %s', new_name, old_name)

        # author stuff
        self.add_file_state(self.aliases[new_name], new_name, commit, mod)
