import psycopg2

DB_USER = 'root'
DB_PASS = ''

con = psycopg2.connect(dbname='Gierlappen2',
                       user=DB_USER,
                       host='localhost',
                       password=DB_PASS)

SCHEMA = """CREATE SCHEMA IF NOT EXISTS Gierlappen2 AUTHORIZATION root;"""

PROJECTS = """CREATE TABLE IF NOT EXISTS Gierlappen2.projects (
    id          serial PRIMARY KEY,
    name        varchar(255) NOT NULL
);
"""
COMMITS = """CREATE TABLE IF NOT EXISTS Gierlappen2.commits (
    id             serial PRIMARY KEY,
    project_id     integer REFERENCES Gierlappen2.projects (id) ON DELETE CASCADE,
    revision_hash  varchar(255) NOT NULL
);
"""

FILES = """CREATE TABLE IF NOT EXISTS Gierlappen2.files (
    id          serial PRIMARY KEY,
    project_id  integer REFERENCES Gierlappen2.projects (id) ON DELETE CASCADE,
    path        text NOT NULL,
    pmd_data    text
);
"""

# if commits are removed due to project removal we delete everything
# if files are removed we do not remove this
FILES_TO_COMMITS = """CREATE TABLE IF NOT EXISTS Gierlappen2.files_to_commits (
    commit_id   integer REFERENCES Gierlappen2.commits (id) ON DELETE CASCADE,
    file_id     integer REFERENCES Gierlappen2.files (id) ON DELETE RESTRICT
);
"""

cur = con.cursor()
cur.execute(SCHEMA)
cur.execute(PROJECTS)
cur.execute(COMMITS)
cur.execute(FILES)
cur.execute(FILES_TO_COMMITS)
con.commit()
