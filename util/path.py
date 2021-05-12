
import logging
from collections import deque


# lifted from mynbou
class OntdekBaan(object):
    """Simple variant of OntdekBaan which yields the paths via bfs until a break condition is hit or no unvisited nodes remain."""

    def __init__(self, g):
        self._graph = g.copy()
        self._nodes = set()
        self._log = logging.getLogger(self.__class__.__name__)

    def _bfs_paths(self, source, predecessors, break_condition):
        paths = {0: [source]}
        visited = set()

        if source not in self._graph:
            raise Exception('Commit {} is not contained in the commit graph'.format(source))

        queue = deque([(source, predecessors(source))])
        while queue:
            parent, children = queue[0]

            try:
                # iterate over children list
                child = next(children)

                # we keep track of visited pairs so that we do not have common suffixes
                if (parent, child) not in visited:

                    break_child = False
                    if break_condition is not None and break_condition(child):
                        break_child = True

                    # find path which last node is parent, append first child
                    if not break_child:
                        for path_num, nodes in paths.items():
                            if parent == nodes[-1]:
                                paths[path_num].append(child)
                                break
                        else:
                            paths[len(paths)] = [parent, child]

                    visited.add((parent, child))

                    if not break_child:
                        queue.append((child, predecessors(child)))

            # every child iterated
            except StopIteration:
                queue.popleft()
        return paths

    def set_path(self, start, direction='backward', break_condition=None):
        """Set start node and travel direction for the BFS."""
        self._start = start
        self._direction = direction
        self._break_condition = break_condition

    def all_paths(self):
        """Generator that yields all possible paths fomr the given start node and the direction."""
        if self._direction == 'backward':
            paths = self._bfs_paths(self._start, self._graph.predecessors, self._break_condition)

            for path_num, path in paths.items():
                yield path

        elif self._direction == 'forward':
            paths = self._bfs_paths(self._start, self._graph.successors, self._break_condition)

            for path_num, path in paths.items():
                yield path

        else:
            raise Exception('no such direction: {}, please use backward or forward'.format(self._direction))
