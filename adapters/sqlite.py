"""Adapter to the SQLite Database.

This allows the PMD and Pylint connectors to cache their expensive work.
"""

import json
import logging
import os
import sqlite3


class SQLiteDatabaseAdapter():
    """Handles the cache for the PMDConnector.
    We may later switch to a common database, for now this is in one sqlite file per project.
    """

    def __init__(self, config):
        self._log = logging.getLogger('jit.pmd_connector.sqlite')
        db_file = os.path.abspath('./cache/{}_pmd6.sqlite'.format(config.project))

        if config.is_test:
            db_file = ':memory:'

        self._con = sqlite3.connect(db_file)
        self._install_db()

        self._con.row_factory = sqlite3.Row
        self._project_id = self.get_project_id(config.project)

    def __del__(self):
        self._con.close()

    def _install_db(self):
        c = self._con.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS projects (
            id          integer PRIMARY KEY,
            name        varchar(255) NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS commits (
            id             integer PRIMARY KEY,
            project_id     integer REFERENCES projects (id) ON DELETE CASCADE,
            revision_hash  varchar(255) NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS files (
            id          integer PRIMARY KEY,
            project_id  integer REFERENCES projects (id) ON DELETE CASCADE,
            path        text NOT NULL,
            pmd_data    text
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS files_to_commits (
            commit_id   integer REFERENCES commits (id) ON DELETE CASCADE,
            file_id     integer REFERENCES files (id) ON DELETE RESTRICT
        )""")
        self._con.commit()

    def get_project_id(self, project_name):
        """Get project_id from project_name.

        We leave this in for now, even though we save one sqlite per project anyway.
        This might change in the future (see postgresql db).

        :param project_name: name of the project
        :return: project_id
        """
        c = self._con.cursor()
        c.execute("""SELECT * FROM projects WHERE name=?""", (project_name,))
        p = c.fetchone()

        if not p or len(p) == 0:
            self._con.cursor()
            c.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
            self._con.commit()

        self._con.cursor()
        c.execute("SELECT * FROM projects WHERE name=?", (project_name,))
        p = c.fetchone()
        return p['id']

    def get_commit(self, revision_hash):
        """Read commit from the database."""
        ret = {}
        c = self._con.cursor()
        c.execute("SELECT f.* FROM projects p, commits c, files f, files_to_commits ftc WHERE p.id = c.project_id AND c.id = ftc.commit_id AND ftc.file_id = f.id AND p.id = ? AND c.revision_hash = ?", (self._project_id, revision_hash))
        for f in c.fetchall():
            fdata = json.loads(f['pmd_data'])
            ret[f['path']] = {'lloc': fdata['lloc'], 'warning_list': fdata['warning_list'], 'warnings': fdata['warnings']}
        return ret

    def save_commit(self, revision_hash, files):
        """Save the commit to the database."""
        c = self._con.cursor()
        c.execute("SELECT count(c.revision_hash) as num_ref FROM commits as c, projects as p WHERE c.project_id = p.id AND p.id = ? AND c.revision_hash = ?", (self._project_id, revision_hash))
        res = c.fetchone()
        c.close()

        if res['num_ref'] == 0:
            self._log.debug('[%s] commit does not exit in table, creating', revision_hash)

            # 0. commit does not exist insert it
            c = self._con.cursor()
            c.execute("INSERT INTO commits (project_id, revision_hash) VALUES (?, ?)", (self._project_id, revision_hash))
            self._con.commit()
            c.close()

            c = self._con.cursor()
            c.execute("SELECT * FROM commits WHERE project_id=? AND revision_hash=?", (self._project_id, revision_hash))
            commit = c.fetchone()
            c.close()

            # 1. insert files only if data does not change
            for path, data in files.items():
                # 1.1. check if files are already in the data with the same values
                c = self._con.cursor()
                c.execute("SELECT f.id as id FROM files f WHERE f.path = ? AND f.pmd_data = ? AND f.project_id = ?", (path, json.dumps(data), self._project_id))
                f = c.fetchone()
                c.close()
                if f:
                    file_id = f['id']
                    # self._log.debug('File %s exist in table files without changes, using id', path)
                else:
                    self._log.debug('[%s] File %s does not exist without changes, creating', revision_hash, path)
                    c = self._con.cursor()
                    c.execute("INSERT INTO files (path, project_id, pmd_data) VALUES (?, ?, ?)", (path, self._project_id, json.dumps(data)))
                    self._con.commit()
                    last_id = c.lastrowid
                    c.close()

                    c = self._con.cursor()
                    c.execute("SELECT id FROM files WHERE id=?", (last_id,))
                    f = c.fetchone()
                    file_id = f['id']
                    c.close()

                # 2. add file_ids from all files in files.keys()
                c = self._con.cursor()
                c.execute("INSERT INTO files_to_commits (file_id, commit_id) VALUES (?, ?)", (file_id, commit['id']))
                self._con.commit()
                c.close()
