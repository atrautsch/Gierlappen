
import argparse
import timeit
import tarfile
import os

from mongoengine import connect
from pycoshark.mongomodels import Project, VCSSystem

def main(args):

    if not args.path.endswith('/'):
        args.path += '/'

    start = timeit.default_timer()

    loc = {'host': args.db_host,
           'port': int(args.db_port),
           'db': args.db_name,
           'username': args.db_user,
           'password': args.db_pw,
           'authentication_source': args.db_auth,
           'connect': False}
    connect(**loc)

    print(args.project, end=' ')

    project = Project.objects.get(name=args.project)
    vcs_system = VCSSystem.objects.get(project_id=project.id)

    # fetch file
    repository = vcs_system.repository_file

    if repository.grid_id is None:
        raise Exception('no repository file for project!')

    fname = '{}.tar.gz'.format(args.project)

    # extract from gridfs
    with open(fname, 'wb') as f:
        f.write(repository.read())

    # extract tarfile
    with tarfile.open(fname, "r:gz") as tar_gz:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar_gz, args.path)

    # remove tarfile
    os.remove(fname)

    end = timeit.default_timer() - start
    print('finished in {:.5f}'.format(end))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract repository dumps from the SmartSHARK database.')
    parser.add_argument('--project', help='Name of the project to extract', required=True)
    parser.add_argument('--path', help='Path to which the repository should be extracted (without the project, e.g., /srv/repos/)', required=True)

    parser.add_argument('--db-host', help='Database host', required=True)
    parser.add_argument('--db-port', help='Database port', required=True)
    parser.add_argument('--db-name', help='Database name', required=True)
    parser.add_argument('--db-user', help='Database user', required=True)
    parser.add_argument('--db-pw', help='Database pw', required=True)
    parser.add_argument('--db-auth', help='Database authentication source', required=True)

    args = parser.parse_args()

    main(args)
