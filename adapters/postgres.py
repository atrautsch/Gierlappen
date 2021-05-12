"""Adapter for the postgresql database for PMD."""

import json
import logging
import psycopg2
import psycopg2.extras


class PostgresDatabaseAdapter():

    def __init__(self, config):
        self._log = logging.getLogger('jit.pmd_connector.postgresql')
        self._con = psycopg2.connect(dbname=config.pg_name,
                                     user=config.pg_user,
                                     host=config.pg_host,
                                     password=config.pg_pw,
                                     options='-c search_path=' + config.pg_schema,
                                     )

        self._project_id = self.get_project_id(config.project)

    def get_project_id(self, project_name):

        with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute("""SELECT * FROM projects WHERE name=%s""", (project_name,))
            p = c.fetchone()

        if not p:
            with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                c.execute("INSERT INTO projects (name) VALUES (%s)", (project_name,))
                self._con.commit()

        with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute("SELECT * FROM projects WHERE name=%s", (project_name,))
            p = c.fetchone()
        return p['id']

    def get_commit(self, revision_hash):
        """Fetch commit from database."""
        ret = {}
        with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute("SELECT f.* FROM Gierlappen2.projects p, Gierlappen2.commits c, Gierlappen2.files f, Gierlappen2.files_to_commits ftc WHERE p.id = c.project_id AND c.id = ftc.commit_id AND ftc.file_id = f.id AND p.id = %s AND c.revision_hash = %s", (self._project_id, revision_hash))
            for f in c.fetchall():
                fdata = json.loads(f['pmd_data'])
                ret[f['path']] = {'lloc': fdata['lloc'], 'warning_list': fdata['warning_list'], 'warnings': fdata['warnings']}
        return ret

    def save_commit(self, revision_hash, files):
        """Insert data into database for commit."""
        with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute("SELECT count(c.revision_hash) as num_ref FROM Gierlappen2.commits as c, Gierlappen2.projects as p WHERE c.project_id = p.id AND p.id = %s AND c.revision_hash = %s", (self._project_id, revision_hash))
            res = c.fetchone()

        if res['num_ref'] == 0:
            self._log.debug('Commit does not exit in table, creating %s', revision_hash)
            # 0. commit does not exist insert it
            with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                c.execute("INSERT INTO Gierlappen2.commits (project_id, revision_hash) VALUES (%s, %s)", (self._project_id, revision_hash))
                self._con.commit()

            with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                c.execute("SELECT * FROM Gierlappen2.commits WHERE project_id=%s AND revision_hash=%s", (self._project_id, revision_hash))
                commit = c.fetchone()

            # 1. insert files only if data does not change
            for path, data in files.items():
                # 1.1. check if files are already in the data with the same values
                with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                    c.execute("SELECT f.id as id FROM Gierlappen2.files f WHERE f.path = %s AND f.pmd_data = %s AND f.project_id = %s", (path, json.dumps(data), self._project_id))
                    f = c.fetchone()
                if f:
                    file_id = f['id']
                    # self._log.debug('File %s exist in table files without changes, using id', path)
                else:
                    self._log.debug('File %s does not exist without changes, creating', path)
                    with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                        c.execute("INSERT INTO Gierlappen2.files (path, project_id, pmd_data) VALUES (%s, %s, %s)", (path, self._project_id, json.dumps(data)))
                        self._con.commit()

                    with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                        c.execute("SELECT id FROM Gierlappen2.files WHERE path=%s AND pmd_data=%s AND project_id = %s", (path, json.dumps(data), self._project_id))
                        f = c.fetchone()
                    file_id = f['id']

                # 2. add file_ids from all files in files.keys()
                with self._con.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                    c.execute("INSERT INTO Gierlappen2.files_to_commits (file_id, commit_id) VALUES (%s, %s)", (file_id, commit['id']))
                    self._con.commit()
