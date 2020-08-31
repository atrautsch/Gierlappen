import os
import copy

from collections import deque

import networkx as nx
from pydriller import RepositoryMining, GitRepository
from pydriller.domain.commit import ModificationType
from pycoshark.utils import java_filename_filter

from util.path import OntdekBaan
from util.tracking import GlobalState, PathState


class Traversal:

    def __init__(self, project_path, check_files, log, to_date, bug_keywords, is_test=False, quality_keywords=None, connector=False):
        self.project_path = project_path
        if not self.project_path.endswith('/'):
            self.project_path += '/'
        self.to_date = to_date
        self.extensions = [".java"]  # ".pm"
        self.keywords = bug_keywords
        self.check_files = check_files

        self._connector = connector
        self._log = log
        self._quality_keywords = {}
        self._is_test = is_test
        if quality_keywords:
            self._quality_keywords = quality_keywords

    def start(self):

        # checkout current default branch (origin/HEAD)
        gr = GitRepository(self.project_path)
        if not self._is_test:
            gr.repo.git.checkout(gr.repo.refs['origin/HEAD'].commit.hexsha, '--force')

        # build graph
        g = nx.DiGraph()
        orphan_candidates = []
        for commit in RepositoryMining(self.project_path).traverse_commits():
            g.add_node(commit.hash)

        for commit in RepositoryMining(self.project_path).traverse_commits():
            for parent in commit.parents:
                g.add_edge(parent, commit.hash)

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
                self._log.debug('adding reference {} {}'.format(r.commit.hexsha, r.name))
                branches.append(r.commit.hexsha)

        # get final orphans with paths to origin/head
        orphans = []
        for orphan in orphan_candidates:
            if origin_tip not in g:
                raise Exception(origin_tip, 'not in graph')
            if nx.has_path(g, orphan, origin_tip):
                orphans.append(orphan)

        # OntdekBaan finds all possible paths from origin_tip (usuall master) to all orphans
        c = OntdekBaan(g)
        c.set_path(origin_tip, 'backward')

        path_state = {}  # state on last commits on every path
        global_state = GlobalState(self._log, self.keywords, self._quality_keywords)  # state for project global information, e.g., authors
        commit_cache = {}  # only for split commits
        initial_path_lengths = {}  # only for logging, save the inital length of all paths

        data = []

        needs_cache = set()
        commits = set()
        need_commits = []

        # create deque objects for all paths
        i = 0
        paths = {}
        for path in c.all_paths():  # a path is a list of revision_hashes
            if i in paths.keys():
                self._log.error('path {} already existing!')
                raise
            paths[i] = deque(reversed(path))
            needs_cache.add(path[-1])  # we only need to cache the first
            path_state[i] = PathState(self._log)  # change states are held per path
            need_commits += path
            initial_path_lengths[i] = len(path)
            i += 1

        # final list of branches to add
        add_branches = []
        for branch in branches:
            if branch in need_commits:
                continue

            for oc in orphans:
                if branch in g and nx.has_path(g, oc, branch):
                    add_branches.append(branch)

        # break condition for bfs on branch tips is hitting a commit we already have in our list
        def break_condition(node):
            return node in need_commits

        for source in add_branches:
            c = OntdekBaan(g)
            c.set_path(source, 'backward', break_condition)
            for path in c.all_paths():  # a path is a list of revision_hashes
                # we need to make sure that the first commit of every additional paths is in our commits, otherwise we would not have
                # a pre-filled state for that path
                if path[-1] not in need_commits:
                    parent = next(g.predecessors(path[-1]))
                    path.append(parent)
                    if path[-1] not in need_commits:
                        self._log.error('additional branch path {}, first commit {} not in existing path!'.format(i, path[-1]))
                        raise  # this is critical

                if i in paths.keys():
                    self._log.error('path {} already existing!')
                    raise

                paths[i] = deque(reversed(path))
                needs_cache.add(path[-1])  # we only need to cache the first
                path_state[i] = PathState(self._log)
                need_commits += path
                initial_path_lengths[i] = len(path)
                i += 1
        need_commits = set(need_commits)
        self._log.debug('finished adding the rest of the paths')

        # add list of dates so that we can traverse by date
        dates = []
        for commit in RepositoryMining(self.project_path).traverse_commits():
            if commit.hash in need_commits:
                dates.append(commit.committer_date)
        dates = sorted(dates)
        self._log.debug('finished collecting dates')

        empty_cycle = 0
        min_date = max(dates)  # minimum path of all dates
        min_path_date = max(dates)  # minimum date of current paths

        # TODO: SEMANTIC CHANGES!!!
        # grab inducings
        self._log.info('loading inducing changes')

        inducings = self.get_adhoc_labels()
        inducing_commits, inducing_files = self.get_unique_bics()

        its_labels = {}
        if self._connector:
            its_labels = self._connector.get_labels()

        self._log.info('finished inducing changes')

        # pre cache connector
        if self._connector:
            self._log.info('cache commits')
            self._connector.pre_cache(need_commits)
            self._log.info('finished caching commits')

        # traverse paths
        while len(need_commits) != len(commits):

            gr2 = GitRepository(self.project_path)  # maybe this will help memory leaks with GitPython/subprocess somewhat

            for pathnum, que in paths.items():
                self._log.info('starting path {} ({}/{}), {}/{} commits'.format(pathnum, initial_path_lengths[pathnum] - len(que), initial_path_lengths[pathnum], len(commits), len(need_commits)))
                while que:
                    revision_hash = que.popleft()
                    c = gr2.get_commit(revision_hash)

                    # we require that we have seen all parents, otherwise we put the commit back on the stack
                    requeue = False
                    for parent in c.parents:
                        if parent not in commits:
                            self._log.info('[{}] requeue, parent {} is not finished'.format(revision_hash, parent))
                            requeue = True
                            break

                    # next case, if the commit needs cache because it is the first on a path but the cache is not yet filled
                    # we assume that another path needs to fill the cache first for that commit
                    # the only exception from this rule are origin commits
                    if revision_hash not in commits and revision_hash in needs_cache and len(c.parents) > 0 and initial_path_lengths[pathnum] == len(que) + 1:
                        self._log.info('[{}] requeue, the commit is the first on path {} and not an orphan commit but the cache is not yet filled'.format(revision_hash, pathnum))
                        requeue = True

                    # if we could use the commit (cache is filled and parent is finished) we set the min_path_date
                    if revision_hash not in commits and not requeue and c.committer_date < min_path_date:
                        min_path_date = c.committer_date

                    # we want to traverse all paths in date order, if the current commit is not the next in date order we put it back on the stack
                    if revision_hash not in commits and c.committer_date != dates[0]:
                        self._log.info('[{}] requeue, commit date is unequal to next date in date-order list {} != {}'.format(revision_hash, c.committer_date, dates[0]))
                        # set min date we want to use if we have multiple passes
                        if min_date > c.committer_date:
                            min_date = c.committer_date
                        self._log.info('[{}] empty_cycle {} min_date {}, min_path_date {}'.format(revision_hash, empty_cycle, min_date, min_path_date))

                        # if we are moving around in circles without finishing anything because of the date we are using
                        # the next minimum date of the last cycle is used (the next node we can use with minimum date)
                        if empty_cycle > 1 and c.committer_date == min_path_date:
                            self._log.info('[{}] switching date in date-order list {} != {}'.format(revision_hash, c.committer_date, dates[0]))
                            tmp = dates.index(min_path_date)
                            dates[0], dates[tmp] = dates[tmp], dates[0]
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
                        que.appendleft(revision_hash)
                        break

                    # if we neede cache we load it
                    if revision_hash in commits and revision_hash in needs_cache:
                        old_files = len(path_state[pathnum].files.keys())
                        path_state[pathnum] = PathState(self._log, files=copy.deepcopy(commit_cache[revision_hash].files))
                        new_files = len(path_state[pathnum].files.keys())
                        self._log.info('[{}] load from cache, files {} -> {}'.format(revision_hash, old_files, new_files))

                    # skip on already extracted commits
                    if revision_hash in commits:
                        continue

                    # todo: no longer necessary with above skip
                    # we have double commits for beginning of paths, e.g., when cache is loaded
                    # we skip here because we need to load the path_state first for the next commit on the path
                    track_only = False
                    if revision_hash in commits:
                        track_only = True

                    # case of one parent or none (orphan commit)
                    if len(c.parents) <= 1:

                        # orphan commit
                        parent = None
                        if len(c.parents) == 1:
                            parent = c.parents[0]

                        self._log.info('[{}] non-merge {}/{} commits, {} state files'.format(revision_hash, len(commits) + 1, len(need_commits), len(path_state[pathnum].files.keys())))
                        path_state[pathnum], global_state, metrics = self.mine_commit(path_state[pathnum], global_state, c, parent, track_only, gr2, inducings, inducing_commits, inducing_files, its_labels, self._connector, self.check_files)

                    # case of multiple parents, need to handle merge
                    elif len(c.parents) > 1:
                        needs_cache.add(revision_hash)
                        self._log.info('[{}] merge {}/{} commits, {} state files'.format(revision_hash, len(commits) + 1, len(need_commits), len(path_state[pathnum].files.keys())))
                        path_state[pathnum], global_state, metrics = self.track_merge(commit_cache, c, global_state, gr2, inducings, inducing_commits, inducing_files, its_labels, self._connector, self.check_files)

                    if revision_hash not in commits:
                        if c.committer_date == dates[0]:
                            empty_cycle = 0  # reset empty cycle counter
                            min_date = max(dates)  # reset min_date
                            min_path_date = max(dates)  # reset min_path_date
                            del dates[0]  # pop date
                        else:
                            raise Exception('date mismatch')  # this is critical, we need eveything in date order (at least when possible)

                    # if we have not already collected the metrics add them (if there are any)
                    if revision_hash not in commits and metrics:
                        to_date = self.to_date.replace(tzinfo=c.committer_date.tzinfo)
                        if c.committer_date <= to_date:
                            data += metrics
                    commits.add(revision_hash)

                    # if one of our successors is a merge commit we need to save this commits state global as the merge draws from that not from the path
                    for succ in g.successors(revision_hash):
                        # sc = Commit.objects.only('parents').get(vcs_system_id=vcs.id, revision_hash=succ)
                        sc = gr.get_commit(succ)
                        if len(sc.parents) > 1 and revision_hash not in commit_cache.keys():
                            commit_cache[revision_hash] = PathState(self._log, files=copy.deepcopy(path_state[pathnum].files))
                            self._log.info('[{}] successor ({}) is merge commit, saving global cache'.format(revision_hash, succ))

                    # save cache if this commit needs it (due to beeing first on a path)
                    if revision_hash in needs_cache and revision_hash not in commit_cache.keys():
                        new_files = len(path_state[pathnum].files.keys())
                        commit_cache[revision_hash] = PathState(self._log, files=copy.deepcopy(path_state[pathnum].files))
                        self._log.info('[{}] save to cache, {} files'.format(revision_hash, new_files))

                self._log.info('finished path {} ({}/{}), {}/{} commits'.format(pathnum, initial_path_lengths[pathnum] - len(que), initial_path_lengths[pathnum], len(commits), len(need_commits)))

            # if we have one complete rotation without beeing finished because of date switches
            # we use the minimum date of the available next commits
            empty_cycle += 1

        # the bug matrix might be too memory intensive to build, we pickle what we have beforehand
        # self._log.info('dumping pickle of collected data just in case')
        # with open('./pickle_{}'.format(self.project_name), 'wb') as f:
        #     pickle.dump(data, f)

        # now we can build the bug matrix
        self._log.info('creating bug matrix')
        all_bugs = set()
        for row in data:
            for bug in row['label_adhoc']:
                all_bugs.add(bug)
            if 'label_bug' in row.keys():
                for bug in row['label_bug']:
                    all_bugs.add(bug)

        new_data = []
        for row in data:
            bug_matrix = {k: 0 for k in all_bugs}
            for bug in row['label_adhoc']:
                bug_matrix[bug] = 1

            if 'label_bug' in row.keys():
                for bug in row['label_bug']:
                    bug_matrix[bug] = 1

            # add bug matrix values to row
            for k, v in bug_matrix.items():
                row[k] = v

            # clear lists which were only needed for the construction of bug_matrix from the output
            if 'label_bug' in row.keys():
                del row['label_bug']
            if 'label_adhoc' in row.keys():
                del row['label_adhoc']

            new_data.append(row)
        self._log.info('finished bug matrix')
        return new_data

    def mine_commit(self, path_state, global_state, commit, parent_revision_hash, track_only=False, gr2=False, inducings=False, inducing_commits=False, inducing_files=False, its_inducings=False, smcon=False, check_files=False):
        metrics = []
        global_state.add_commit(commit, inducings, inducing_commits, inducing_files, its_inducings, smcon)
        for m in commit.modifications:
            # this is handled separately in rename
            if m.change_type is not ModificationType.RENAME:

                # restrict only to java files
                if m.new_path and not java_filename_filter(m.new_path, production_only=False):
                    continue
                if m.old_path and not java_filename_filter(m.old_path, production_only=False):
                    continue

            if m.change_type is ModificationType.MODIFY:
                self._log.debug('[{}] modify: {}'.format(commit.hash, m.new_path))
                path_state.modify_file(m.new_path)
                global_state.modify_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.ADD:
                self._log.debug('[{}] add: {}'.format(commit.hash, m.new_path))
                path_state.add_file(m.new_path)
                global_state.add_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.COPY:
                self._log.debug('[{}] add: {}'.format(commit.hash, m.new_path))
                path_state.add_file(m.new_path)
                global_state.add_file(m.new_path, commit, m)
            elif m.change_type is ModificationType.DELETE:
                self._log.debug('[{}] del: {}'.format(commit.hash, m.old_path))
                path_state.del_file(m.old_path)
                global_state.del_file(m.old_path, commit, m)
            elif m.change_type is ModificationType.RENAME:
                self._log.debug('[{}] move: {}->{}'.format(commit.hash, m.old_path, m.new_path))
                # we rename somethign from a not tracked source or to a not tracked source file we need to handle it differently in the states
                if not java_filename_filter(m.new_path, production_only=False) and java_filename_filter(m.old_path, production_only=False):
                    path_state.del_file(m.old_path)
                    global_state.del_file(m.old_path, commit, m)
                if not java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
                    path_state.add_file(m.new_path)
                    global_state.add_file(m.new_path, commit, m)
                if java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
                    path_state.move_file(m.old_path, m.new_path)
                    global_state.move_file(m.old_path, m.new_path, commit, m)
            else:
                self._log.error('[{}] unknown mod type'.format(commit.hash))

        # check state files agains filesystem
        if check_files:
            dir_files = self.get_files(commit, gr2)
            state_files = set(path_state.files.keys())

            a = dir_files - state_files
            b = state_files - dir_files

            if len(a) > 0:
                self._log.error('Files {} in dir_files but not in state_files!'.format(a))
            if len(b) > 0:
                self._log.error('Files {} in state_files but not in dir_files!'.format(b))
            if len(a) > 0 or len(b) > 0:
                raise Exception('stopping here')

        global_state.calculate_metrics(commit)
        metrics = copy.deepcopy(global_state.metrics)
        return path_state, global_state, metrics

    def track_merge(self, commit_cache, commit, global_state, gr2, inducings, inducing_commits, inducing_files, its_inducings, smcon, check_files):
        # pydriller internal options
        options = {}
        if commit._conf.get('histogram'):
            options['histogram'] = True
        if commit._conf.get('skip_whitespaces'):
            options['w'] = True

        global_state.add_commit(commit, inducings, inducing_commits, inducing_files, its_inducings, smcon)

        merged_state = {'files': {}}
        for parent_num, parent_revision_hash in enumerate(commit.parents):
            path_state = PathState(self._log, files=copy.deepcopy(commit_cache[parent_revision_hash].files))  # copy path_state from the parent that we are adding the changes to

            # this gets us the modifications for a specific parent
            diff_index = commit._c_object.parents[parent_num].diff(commit._c_object, create_patch=True, **options)
            for m in commit._parse_diff(diff_index):

                # this is handled separately in rename
                if m.change_type is not ModificationType.RENAME:

                    if m.new_path and not java_filename_filter(m.new_path, production_only=False):
                        continue
                    if m.old_path and not java_filename_filter(m.old_path, production_only=False):
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
                    if not java_filename_filter(m.new_path, production_only=False) and java_filename_filter(m.old_path, production_only=False):
                        path_state.del_file(m.old_path)
                    if not java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
                        path_state.add_file(m.new_path)
                    if java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
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
                        if not java_filename_filter(m.new_path, production_only=False) and java_filename_filter(m.old_path, production_only=False):
                            global_state.del_file(m.old_path, commit, m)
                        if not java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
                            global_state.add_file(m.new_path, commit, m)
                        if java_filename_filter(m.old_path, production_only=False) and java_filename_filter(m.new_path, production_only=False):
                            global_state.move_file(m.old_path, m.new_path, commit, m)

            merged_state['files'].update(**path_state.files)

        # check state files agains filesystem
        if check_files:
            dir_files = self.get_files(commit, gr2)
            state_files = set(merged_state['files'].keys())

            a = dir_files - state_files
            b = state_files - dir_files

            if len(a) > 0:
                self._log.error('Files {} in dir_files but not in state_files!'.format(a))
            if len(b) > 0:
                self._log.error('Files {} in state_files but not in dir_files!'.format(b))
            if len(a) > 0 or len(b) > 0:
                raise Exception('stopping here')

        global_state.calculate_metrics(commit)
        metrics = copy.deepcopy(global_state.metrics)

        # we need to return the merged parent states in a new path_state
        return PathState(self._log, files=merged_state['files']), global_state, metrics

    def get_adhoc_labels(self):
        """Return adhoc fixes, labels after Pascarella et al. keyword based"""
        inducings = {}
        gr = GitRepository(self.project_path)
        gr2 = GitRepository(self.project_path)
        for commit in RepositoryMining(self.project_path, only_no_merge=True, only_modifications_with_file_types=self.extensions).traverse_commits():
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

                if not java_filename_filter(fix['file'], production_only=False):
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
        for commit in RepositoryMining(self.project_path, to=self.to_date, only_no_merge=True, only_modifications_with_file_types=self.extensions).traverse_commits():
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
                    if not dout['path'].endswith(tuple(self.extensions)):
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
        """Returns a all files for a commit.

        We use this to find errors in our file tracking, e.g., files appear without beeing added before or files are missing without beeing deleted before.
        """
        gr2.repo.git.checkout(commit.hash, '--force')

        result = set()
        for root, dirs, files in os.walk(self.project_path):
            for file in files:
                filepath = os.path.join(root, file)
                rel_filepath = filepath.replace(self.project_path, '')

                if java_filename_filter(rel_filepath, production_only=False):
                    result.add(rel_filepath)

        if not self._is_test:
            gr2.repo.git.checkout(gr2.repo.refs['origin/HEAD'].commit.hexsha, '--force')
        return result
