"""This module contains the classes for aggregating traversal data and
traversing the commit graph."""
import os
import copy
import logging
import hashlib
import pickle
import pprint

from collections import deque

import networkx as nx
from pydriller import RepositoryMining, GitRepository
from pydriller.domain.commit import ModificationType

from connectors.linter import LinterConnector
from connectors.build import PomPom
from util.path import OntdekBaan
from util.tracking import GlobalState, PathState


class TraversalState:
    """Holds state of the traversal process."""

    def __init__(self, config):
        self.data = []  # the mining results, features and labels
        self.paths = {}  # the path queues
        self.path_state = {}  # state on last commits on every path
        self.global_state = GlobalState(config)  # state for project global information, e.g., authors
        self.commit_cache = {}  # only for split commits
        self.initial_path_lengths = {}  # only for logging, save the inital length of all paths
        self.needs_cache = set()
        self.commits = set()
        self.need_commits = []
        self.labels = []  # we need those for the bug matrix later
        self.g = nx.DiGraph()

        self.dates = []
        self.min_date = 0
        self.min_path_date = 0

    def save(self, filename):
        """Dump the state so that the process can resume later."""
        with open(filename, 'wb') as f:
            pickle.dump(self, f)

    # TODO: can we do this better?
    @classmethod
    def load(cls, filename):
        with  open(filename, 'rb') as f:
            ts = pickle.load(f)
        return ts


class Traversal:

    # def __init__(self, project_name, project_path, check_files, to_date, bug_keywords, is_test=False, quality_keywords=None, connector=False, only_production=False, use_pmd=False, use_maven=False):
    def __init__(self, args):
        self.project_path = args.path
        if not self.project_path.endswith('/'):
            self.project_path += '/'
        self.to_date = args.to_date

        self._extensions = args.extensions
        self.keywords = args.keywords
        self.project_name = args.project

        self._args = args
        self._check_files = args.file_check
        self._log = logging.getLogger('jit.traversal')
        self._connector = args.connector
        self._quality_keywords = {}
        self._is_test = args.is_test
        self._production_only = args.production_only
        self._use_linter = args.use_linter
        self._use_maven = args.use_maven
        if args.quality_keywords:
            self._quality_keywords = args.quality_keywords

    def update_graph(self, ts):
        """Update the graph with new data (new commits)."""
        # 1. create graph
        fresh_ts = self.create_graph()

        # 2. mark commits we already have from the paths until we are at old state
        for commit in ts.commits:
            fresh_ts.commits.add(commit)

        # todo: this is probably not the best way to do it, maybe ditch dates altogether or only as tie breaker?
        fresh_ts.dates = [date for date in fresh_ts.dates if date > ts.min_path_date]
        fresh_ts.data = ts.data
        fresh_ts.min_path_date = ts.min_path_date
        fresh_ts.min_date = ts.min_date
        fresh_ts.commit_cache = ts.commit_cache
        #fresh_ts.labels = ts.labels
        fresh_ts.global_state = ts.global_state
        fresh_ts.path_state = ts.path_state
        fresh_ts.needs_cache.update(ts.needs_cache)

        return fresh_ts

    def _hash_path(self, path):
        """as a key we hash the first and second revision_hash for each path"""
        ph = hashlib.sha1()
        ph.update(path[-1].encode())
        ph.update(path[-2].encode())
        return ph.hexdigest()

    def create_graph(self):
        """Reads the repository structure, returns a TraversalState."""

        ts = TraversalState(self._args)

        # checkout current default branch (origin/HEAD)
        gr = GitRepository(self.project_path)
        if not self._is_test:
            gr.repo.git.checkout(gr.repo.refs['origin/HEAD'].commit.hexsha, '--force')

        # build graph
        orphan_candidates = []
        for commit in RepositoryMining(self.project_path).traverse_commits():
            ts.g.add_node(commit.hash)

        for commit in RepositoryMining(self.project_path).traverse_commits():
            for parent in commit.parents:
                ts.g.add_edge(parent, commit.hash)

            # collect orphans along the way
            if not commit.parents:
                orphan_candidates.append(commit.hash)

        # get origin/head and all branches (except for test where we only have local repos)
        if not self._is_test:
            origin_tip = gr.repo.refs['origin/HEAD'].commit.hexsha
        if self._is_test:
            origin_tip = gr.repo.refs['master'].commit.hexsha

        branches = []
        for r in gr.repo.refs:
            if r.commit.hexsha != origin_tip:
                self._log.debug('adding reference %s %s', r.commit.hexsha, r.name)
                branches.append(r.commit.hexsha)

        # get final orphans with paths to origin/head
        orphans = []
        for orphan in orphan_candidates:
            if origin_tip not in ts.g:
                raise Exception(origin_tip, 'not in graph')
            if nx.has_path(ts.g, orphan, origin_tip):
                orphans.append(orphan)

        # OntdekBaan finds all possible paths from origin_tip (usually master) to all orphans
        c = OntdekBaan(ts.g)
        c.set_path(origin_tip, 'backward')

        # create deque objects for all paths
        for path in c.all_paths():  # a path is a list of revision_hashes
            key = self._hash_path(path)
            if key in ts.paths.keys():
                self._log.error('path %s already existing!', key)
                raise Exception('path {} already existing!'.format(key))
            ts.paths[key] = deque(reversed(path))
            ts.needs_cache.add(path[-1])  # we only need to cache the first
            ts.needs_cache.add(path[0])  # and the last if we want to continue
            ts.path_state[key] = PathState()  # change states are held per path
            ts.need_commits += path
            ts.initial_path_lengths[key] = len(path)

        # final list of branches to add
        add_branches = []
        for branch in branches:
            if branch in ts.need_commits:
                continue

            for oc in orphans:
                if branch in ts.g and nx.has_path(ts.g, oc, branch):
                    add_branches.append(branch)

        # break condition for bfs on branch tips is hitting a commit we already have in our list
        def break_condition(node):
            return node in ts.need_commits

        for source in add_branches:
            c = OntdekBaan(ts.g)
            c.set_path(source, 'backward', break_condition)
            for path in c.all_paths():  # a path is a list of revision_hashes

                key = self._hash_path(path)
                # we need to make sure that the first commit of every additional paths is in our commits, otherwise we would not have
                # a pre-filled state for that path
                if path[-1] not in ts.need_commits:
                    parent = next(ts.g.predecessors(path[-1]))
                    path.append(parent)
                    if path[-1] not in ts.need_commits:
                        self._log.error('additional branch path %s, first commit %s not in existing path!', key, path[-1])
                        raise Exception('additional branch path {}, first commit {} is not in existing path'.format(key, path[-1])) # this is critical

                if key in ts.paths.keys():
                    self._log.error('path %s already existing!', key)
                    raise Exception('path {} already existing'.format(key))  # this is also critical

                ts.paths[key] = deque(reversed(path))
                ts.needs_cache.add(path[-1])  # we only need to cache the first
                ts.needs_cache.add(path[0])  # and the last if we want to continue later
                ts.path_state[key] = PathState()
                ts.need_commits += path
                ts.initial_path_lengths[key] = len(path)
        ts.need_commits = set(ts.need_commits)
        self._log.debug('finished adding the rest of the paths')

        # add list of dates so that we can traverse by date
        dates = []
        for commit in RepositoryMining(self.project_path).traverse_commits():
            if commit.hash in ts.need_commits:
                dates.append(commit.committer_date)
        ts.dates = sorted(dates)
        self._log.debug('finished collecting dates')

        ts.min_date = max(ts.dates)  # minimum path of all dates
        ts.min_path_date = max(ts.dates)  # minimum date of current paths

        return ts

    def traverse(self, ts):
        """Run the actual traversal on the given state."""
        # used in traversal
        gr = GitRepository(self.project_path)
        if not self._is_test:
            gr.repo.git.checkout(gr.repo.refs['origin/HEAD'].commit.hexsha, '--force')

        # add smartshark connector
        if self._connector:
            ts.global_state.set_smartshark_connector(self._connector)

        # add pmd connector
        if self._use_linter:
            linter_con = LinterConnector(self._args)
            ts.global_state.set_linter_connector(linter_con)
            #pmd_cache_file = './cache/{}_pmd6.pickle'.format(self.project_name)
            #if os.path.exists(pmd_cache_file):
            #    pmd_con.load_cache(pmd_cache_file)

        # add build connector
        if self._use_maven:
            pompom = PomPom(self.project_path)
            ts.global_state.set_build_connector(pompom)
            build_cache_file = './cache/{}_build.pickle'.format(self.project_name)
            if os.path.exists(build_cache_file):
                pompom.load_cache(build_cache_file)

        # grab inducings
        self._log.info('loading inducing changes')

        # we may need a type of connector architecture here too
        #if self._use_github_issues:
        #    pass

        inducings = self.get_adhoc_labels()
        inducing_commits, inducing_files = self.get_unique_bics()

        ts.global_state.set_adhoc_inducing(inducings)
        ts.global_state.set_inducing_commits(inducing_commits)
        ts.global_state.set_inducing_files(inducing_files)

        if self._connector:
            for label, label_data in self._connector.get_labels().items():
                self._log.info('saving labels for %s', label)
                ts.global_state.set_its_inducing(label, label_data)
                ts.labels.append(label)
        self._log.info('finished inducing changes')

        # pre cache connector
        if self._connector:
            self._log.info('cache commits')
            self._connector.pre_cache(ts.need_commits)
            self._log.info('finished caching commits')

        # traverse paths
        empty_cycle = 0
        while len(ts.need_commits) != len(ts.commits):

            gr2 = GitRepository(self.project_path)  # maybe this will help memory leaks with GitPython/subprocess somewhat

            for pathnum, (pathkey, que) in enumerate(ts.paths.items()):

                # skip if we have nothing to do on this path
                if len(que) == 0:
                    self._log.debug('skipping path %s (%s/%s), %s/%s commits, nothing to do', pathnum, ts.initial_path_lengths[pathkey] - len(que), ts.initial_path_lengths[pathkey], len(ts.commits), len(ts.need_commits))

                    continue

                self._log.info('starting path %s (%s/%s), %s/%s commits', pathnum, ts.initial_path_lengths[pathkey] - len(que), ts.initial_path_lengths[pathkey], len(ts.commits), len(ts.need_commits))
                while que:

                    metrics = {}
                    revision_hash = que.popleft()
                    c = gr2.get_commit(revision_hash)

                    # we require that we have seen all parents, otherwise we put the commit back on the stack
                    requeue = False
                    for parent in c.parents:
                        if parent not in ts.commits:
                            self._log.info('[%s] requeue, parent %s is not finished', revision_hash, parent)
                            requeue = True
                            break

                    # next case, if the commit needs cache because it is the first on a path but the cache is not yet filled
                    # we assume that another path needs to fill the cache first for that commit
                    # the only exception from this rule are origin commits
                    if not requeue and revision_hash not in ts.commits and revision_hash in ts.needs_cache and len(c.parents) > 0 and ts.initial_path_lengths[pathkey] == len(que) + 1:
                        self._log.info('[%s] requeue, the commit is the first on path %s and not an orphan commit but the cache is not yet filled', revision_hash, pathnum)
                        requeue = True

                    # if we could use the commit (cache is filled and parent is finished) we set the min_path_date
                    if not requeue and revision_hash not in ts.commits and not requeue and c.committer_date < ts.min_path_date:
                        ts.min_path_date = c.committer_date

                    # we want to traverse all paths in date order, if the current commit is not the next in date order we put it back on the stack
                    if not requeue and revision_hash not in ts.commits and c.committer_date != ts.dates[0]:
                        self._log.info('[%s] requeue, commit date is unequal to next date in date-order list %s != %s', revision_hash, c.committer_date, ts.dates[0])
                        # set min date we want to use if we have multiple passes
                        if ts.min_date > c.committer_date:
                            ts.min_date = c.committer_date
                        self._log.info('[%s] empty_cycle %s min_date %s, min_path_date %s', revision_hash, empty_cycle, ts.min_date, ts.min_path_date)

                        # if we are moving around in circles without finishing anything because of the date we are using
                        # the next minimum date of the last cycle is used (the next node we can use with minimum date)
                        if empty_cycle > 1 and c.committer_date == ts.min_path_date:
                            self._log.info('[%s] switching date in date-order list %s != %s', revision_hash, c.committer_date, ts.dates[0])
                            tmp = ts.dates.index(ts.min_path_date)
                            ts.dates[0], ts.dates[tmp] = ts.dates[tmp], ts.dates[0]
                        else:
                            requeue = True
                            # if we are further along the cycle and still hit this we chose the minimum date of all currently queued commits
                            # if empty_cycle > 3 and c.committer_date == min_path_date:
                            #     log.info('[{}] min_path_date trigger, switching date in date-order list {} != {}'.format(revision_hash, c.committer_date, dates[0]))
                            #     tmp = dates.index(min_path_date)
                            #     dates[0], dates[tmp] = dates[tmp], dates[0]
                            # else:
                            #     requeue = True

                    # if we need to requeue we better also jump to the next path number
                    if requeue:
                        self._log.debug('[%s] putting back on stack', revision_hash)
                        que.appendleft(revision_hash)
                        break

                    # if we neede cache we load it
                    if revision_hash in ts.commits and revision_hash in ts.needs_cache:
                        old_files = len(ts.path_state[pathkey].files.keys())
                        ts.path_state[pathkey] = PathState(files=copy.deepcopy(ts.commit_cache[revision_hash].files))
                        new_files = len(ts.path_state[pathkey].files.keys())
                        self._log.info('[%s] load from cache, files %s -> %s', revision_hash, old_files, new_files)

                    # skip on already extracted commits
                    if revision_hash in ts.commits:
                        self._log.debug('[%s] already extracted, skipping', revision_hash)
                        continue

                    # case of one parent or none (orphan commit)
                    if len(c.parents) <= 1:

                        # orphan commit
                        parent = None
                        if len(c.parents) == 1:
                            parent = c.parents[0]

                        self._log.info('[%s] non-merge %s/%s commits, %s state files', revision_hash, len(ts.commits) + 1, len(ts.need_commits), len(ts.path_state[pathkey].files.keys()))
                        ts.path_state[pathkey], ts.global_state, metrics = self.mine_commit(ts.path_state[pathkey], ts.global_state, c, parent)

                    # case of multiple parents, need to handle merge
                    elif len(c.parents) > 1:
                        ts.needs_cache.add(revision_hash)
                        self._log.info('[%s] merge %s/%s commits, %s state files', revision_hash, len(ts.commits) + 1, len(ts.need_commits), len(ts.path_state[pathkey].files.keys()))
                        ts.path_state[pathkey], ts.global_state, metrics = self.track_merge(ts.commit_cache, c, ts.global_state)

                    if revision_hash not in ts.commits:
                        if c.committer_date == ts.dates[0]:
                            empty_cycle = 0  # reset empty cycle counter
                            ts.min_date = max(ts.dates)  # reset min_date
                            ts.min_path_date = max(ts.dates)  # reset min_path_date
                            del ts.dates[0]  # pop date
                        else:
                            raise Exception('date mismatch')  # this is critical, we need eveything in date order (at least when possible)

                    # if we have not already collected the metrics add them (if there are any), to_date is maximum date only add if current date is below that
                    if revision_hash not in ts.commits and metrics:
                        to_date = self.to_date.replace(tzinfo=c.committer_date.tzinfo)
                        if c.committer_date <= to_date:
                            # append aditional path information
                            for m in metrics:
                                m['pathnum'] = pathnum
                                ts.data.append(m)

                            # self._log.info('[%s] %s/%s commits, memsize commit cache: %s mb', revision_hash, len(ts.commits) + 1, len(ts.need_commits), asizeof.asizeof(ts.global_state._wd_cache) / 1024 / 1024)
                            # self._log.info('[%s] %s/%s commits, memsize metrics: %s mb, memsize static metrics: %s mb', revision_hash, len(ts.commits) + 1, len(ts.need_commits), asizeof.asizeof(ts.data) / 1024 / 1024, asizeof.asizeof(ts.global_state.files) / 1024 / 1024)
                            # ts.data += metrics
                    # add commits to set of finished commits
                    ts.commits.add(revision_hash)

                    # if one of our successors is a merge commit we need to save this commits state global as the merge draws from that not from the path
                    for succ in ts.g.successors(revision_hash):
                        sc = gr.get_commit(succ)
                        if len(sc.parents) > 1 and revision_hash not in ts.commit_cache.keys():
                            ts.commit_cache[revision_hash] = PathState(files=copy.deepcopy(ts.path_state[pathkey].files))
                            self._log.info('[%s] successor (%s) is merge commit, saving global cache', revision_hash, succ)

                    # save cache if this commit needs it (due to beeing first on a path)
                    if revision_hash in ts.needs_cache and revision_hash not in ts.commit_cache.keys():
                        new_files = len(ts.path_state[pathkey].files.keys())
                        ts.commit_cache[revision_hash] = PathState(files=copy.deepcopy(ts.path_state[pathkey].files))
                        self._log.info('[%s] save to cache, %s files', revision_hash, new_files)

                self._log.info('finished path %s (%s/%s), %s/%s commits', pathnum, ts.initial_path_lengths[pathkey] - len(que), ts.initial_path_lengths[pathkey], len(ts.commits), len(ts.need_commits))

            # if we have one complete rotation without beeing finished because of date switches
            # we use the minimum date of the available next commits
            empty_cycle += 1

        # the bug matrix might be too memory intensive to build, we pickle what we have beforehand
        # self._log.info('dumping pickle of collected data just in case')
        # with open('./pickle_{}'.format(self.project_name), 'wb') as f:
        #     pickle.dump(data, f)

        if self._use_maven:
            pompom.save_cache(build_cache_file)


        # we need to re-attach the inducings here in case we loaded a previous traversal state
        for row in ts.data:
            needle = '{}__{}'.format(row['commit'], row['file'])
            row['label_adhoc'] = inducings.get(needle, [])

        # now we can build the bug matrix
        self._log.info('creating bug matrix')
        all_bugs = set()
        for row in ts.data:
            if 'label_adhoc' not in row.keys():
                print(row)
            for bug in row['label_adhoc']:
                all_bugs.add(bug)
            #if 'label_bug' in row.keys():
            for label in ts.labels:
                for bug in row['label_{}'.format(label)]:
                    all_bugs.add('{}__{}'.format(label, bug))

        new_data = []
        for row in ts.data:
            bug_matrix = {k: 0 for k in all_bugs}
            for bug in row['label_adhoc']:
                bug_matrix[bug] = 1

            #if 'label_bug' in row.keys():
            for label in ts.labels:
                for bug in row['label_{}'.format(label)]:
                    bug_matrix['{}__{}'.format(label, bug)] = 1
            # add bug matrix values to row
            for k, v in bug_matrix.items():
                row[k] = v

            # clear lists which were only needed for the construction of bug_matrix from the output
            #if 'label_bug' in row.keys():
            for label in ts.labels:
                del row['label_{}'.format(label)]
            if 'label_adhoc' in row.keys():
                del row['label_adhoc']

            new_data.append(row)
        self._log.info('finished bug matrix')
        return new_data

    def mine_commit(self, path_state, global_state, commit, parent_revision_hash):
        metrics = []

        gr2 = GitRepository(self.project_path)
        gr2.repo.git.checkout(commit.hash, '--force')  # we rely on the current filesystem of the project being the current commit in PMD and build connectors
        global_state.add_commit(commit)
        for m in commit.modifications:
            # this is handled separately in rename
            if m.change_type is not ModificationType.RENAME:

                # restrict only to java files
                if m.new_path and not self._args.filename_filter(m.new_path):
                    continue
                if m.old_path and not self._args.filename_filter(m.old_path):
                    continue

            if m.change_type is ModificationType.MODIFY:
                self._log.debug('[%s] modify: %s', commit.hash, m.new_path)
                path_state.modify_file(m.new_path)
                global_state.modify_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.ADD:
                self._log.debug('[%s] add: %s', commit.hash, m.new_path)
                path_state.add_file(m.new_path)
                global_state.add_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.COPY:
                self._log.debug('[%s] add: %s', commit.hash, m.new_path)
                path_state.add_file(m.new_path)
                global_state.add_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.DELETE:
                self._log.debug('[%s] del: %s', commit.hash, m.old_path)
                path_state.del_file(m.old_path)
                global_state.del_file(m.old_path, commit, m)
            elif m.change_type is ModificationType.RENAME:
                self._log.debug('[%s] move: %s->%s', commit.hash, m.old_path, m.new_path)
                # we rename somethign from a not tracked source or to a not tracked source file we need to handle it differently in the states
                if not self._args.filename_filter(m.new_path) and self._args.filename_filter(m.old_path):
                    path_state.del_file(m.old_path)
                    global_state.del_file(m.old_path, commit, m)
                if not self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                    path_state.add_file(m.new_path)
                    global_state.add_file(m.new_path, commit, m)
                if self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                    path_state.move_file(m.old_path, m.new_path)
                    global_state.move_file(m.old_path, m.new_path, commit, m)
            else:
                self._log.error('[%s] unknown mod type %s', commit.hash, m.change_type)

        # check state files agains filesystem
        if self._check_files:
            dir_files = self.get_files(commit, gr2)
            state_files = set(path_state.files.keys())

            a = dir_files - state_files
            b = state_files - dir_files

            if len(a) > 0:
                self._log.error('Files %s in dir_files but not in state_files!', a)
            if len(b) > 0:
                self._log.error('Files %s in state_files but not in dir_files!', b)
            if len(a) > 0 or len(b) > 0:
                raise Exception('stopping here')

        global_state.calculate_metrics(commit)
        metrics = copy.deepcopy(global_state.metrics)
        return path_state, global_state, metrics

    def track_merge(self, commit_cache, commit, global_state):

        # pydriller internal options
        options = {}
        if commit._conf.get('histogram'):
            options['histogram'] = True
        if commit._conf.get('skip_whitespaces'):
            options['w'] = True

        global_state.add_commit(commit)

        merged_state = {'files': {}}
        for parent_num, parent_revision_hash in enumerate(commit.parents):
            path_state = PathState(files=copy.deepcopy(commit_cache[parent_revision_hash].files))  # copy path_state from the parent that we are adding the changes to

            # this gets us the modifications for a specific parent
            diff_index = commit._c_object.parents[parent_num].diff(commit._c_object, create_patch=True, **options)
            for m in commit._parse_diff(diff_index):

                # this is handled separately in rename
                if m.change_type is not ModificationType.RENAME:

                    if m.new_path and not self._args.filename_filter(m.new_path):
                        continue
                    if m.old_path and not self._args.filename_filter(m.old_path):
                        continue

                if m.change_type == ModificationType.MODIFY:
                    path_state.modify_file(m.new_path)
                elif m.change_type is ModificationType.ADD:
                    path_state.add_file(m.new_path)
                elif m.change_type is ModificationType.COPY:
                    path_state.add_file(m.new_path)
                elif m.change_type is ModificationType.DELETE:
                    path_state.del_file(m.old_path)
                elif m.change_type is ModificationType.RENAME:
                    if not self._args.filename_filter(m.new_path) and self._args.filename_filter(m.old_path):
                        path_state.del_file(m.old_path)
                    if not self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                        path_state.add_file(m.new_path)
                    if self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                        path_state.move_file(m.old_path, m.new_path)

                # first parent is not yet traversed?
                # if not global state is missing here
                if parent_num == 0:
                    if m.change_type == ModificationType.MODIFY:
                        global_state.modify_file(m.new_path, commit, m)
                    elif m.change_type is ModificationType.ADD:
                        global_state.add_file(m.new_path, commit, m)
                    elif m.change_type is ModificationType.COPY:
                        global_state.add_file(m.new_path, commit, m)
                    elif m.change_type is ModificationType.DELETE:
                        global_state.del_file(m.old_path, commit, m)
                    elif m.change_type is ModificationType.RENAME:
                        # we rename somethign from a not tracked source or to a not tracked source file
                        if not self._args.filename_filter(m.new_path) and self._args.filename_filter(m.old_path):
                            global_state.del_file(m.old_path, commit, m)
                        if not self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                            global_state.add_file(m.new_path, commit, m)
                        if self._args.filename_filter(m.old_path) and self._args.filename_filter(m.new_path):
                            global_state.move_file(m.old_path, m.new_path, commit, m)

            merged_state['files'].update(**path_state.files)

        # check state files agains filesystem
        if self._check_files:
            gr2 = GitRepository(self.project_path)
            dir_files = self.get_files(commit, gr2)
            state_files = set(merged_state['files'].keys())

            a = dir_files - state_files
            b = state_files - dir_files

            if len(a) > 0:
                self._log.error('Files %s in dir_files but not in state_files!', a)
            if len(b) > 0:
                self._log.error('Files %s in state_files but not in dir_files!', b)
            if len(a) > 0 or len(b) > 0:
                raise Exception('stopping here')

        global_state.calculate_metrics(commit)
        metrics = copy.deepcopy(global_state.metrics)

        # we need to return the merged parent states in a new path_state
        return PathState(files=merged_state['files']), global_state, metrics

    def get_adhoc_labels(self):
        """Return adhoc fixes, labels after Pascarella et al. keyword based"""
        inducings = {}
        gr = GitRepository(self.project_path)
        gr2 = GitRepository(self.project_path)
        for commit in RepositoryMining(self.project_path, only_no_merge=True, only_modifications_with_file_types=self._args.extensions).traverse_commits():
            msg = commit.msg.lower()

            # is_oversized = len(commit.modifications) >= 50  we are not using oversized
            is_fix = any(word in msg for word in self.keywords)

            if not is_fix:
                continue

            fix = {'commit': commit.hash, 'committer_date': commit.committer_date}
            for m in commit.modifications:

                # we can not blame added files
                if m.change_type == ModificationType.ADD:
                    continue

                # set current name
                if m.change_type == ModificationType.DELETE:
                    fix['file'] = m.old_path
                else:
                    fix['file'] = m.new_path

                if not self._args.filename_filter(fix['file']):
                    continue

                # collect changed lines for each file changed in bug-fixing commit
                p = m.diff_parsed
                deleted = []
                for dl in p['deleted']:
                    if not gr._useless_line(dl[1].strip()):  # this uses pydrillers removal of comments and whitespaces
                        deleted.append(dl[0])

                # blame this file with newest commit=parent commit (otherwise we would trivially get this current commit) for the file
                # then only find matching lines
                for bi in gr2.repo.blame_incremental('{}^'.format(commit.hash), m.old_path, w=True):
                    for d in deleted:
                        if d in bi.linenos:
                            k = '{}__{}'.format(bi.commit, bi.orig_path)
                            if k not in inducings.keys():
                                inducings[k] = []
                            inducings[k].append('adhoc__{}__{}'.format(fix['commit'], fix['committer_date']))
        return inducings

    def get_unique_bics(self):
        """Basically code from Pascarella et al, composing of both their labels for partial and fully defective commits.

        Matching files in partial defective commits is handled the same as in their paper.
        """
        gr = GitRepository(self.project_path)
        gr2 = GitRepository(self.project_path)

        unique_bics = set()
        unique_bics_files = set()
        for commit in RepositoryMining(self.project_path, to=self.to_date, only_no_merge=True, only_modifications_with_file_types=self._args.extensions).traverse_commits():
            msg = commit.msg.lower()
            mods = commit.modifications
            if len(mods) < 50 and any(word in msg for word in self.keywords):
                dout = {"hash": commit.hash, "size": len(mods), "developer": commit.committer.email, "fix": True}
                for mod in mods:
                    dout["type"] = mod.change_type
                    if mod.change_type == ModificationType.DELETE:
                        dout["path"] = mod.old_path
                    else:
                        dout["path"] = mod.new_path
                    if not dout['path'].endswith(tuple(self._args.extensions)):
                        continue
                    bics_per_mod = gr.get_commits_last_modified_lines(commit, mod)
                    for bic_path, bic_commit_hashs in bics_per_mod.items():
                        dout["bic_path"] = bic_path
                        for bic_commit_hash in bic_commit_hashs:
                            bic = gr2.get_commit(bic_commit_hash)
                            dout["bic_hash"] = bic_commit_hash
                            dout["bic_size"] = len(bic.modifications)
                            unique_bics.add(bic_commit_hash)
                            unique_bics_files.add('{}$${}'.format(bic_commit_hash, bic_path))
        return unique_bics, unique_bics_files

    def get_files(self, commit, gr2):
        """Returns all files for a commit.

        We use this to find errors in our file tracking, e.g., files appear without beeing added before or files are missing without beeing deleted before.
        """
        gr2.repo.git.checkout(commit.hash, '--force')

        result = set()
        for root, dirs, files in os.walk(self.project_path):
            for file in files:
                filepath = os.path.join(root, file)
                rel_filepath = filepath.replace(self.project_path, '')

                if self._args.filename_filter(rel_filepath):
                    result.add(rel_filepath)

        if not self._is_test:
            gr2.repo.git.checkout(gr2.repo.refs['origin/HEAD'].commit.hexsha, '--force')
        return result
