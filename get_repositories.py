
import timeit
import tarfile
import os

from mongoengine import connect
from pycoshark.mongomodels import Project, VCSSystem

loc = {'host': '127.0.0.1',
       'port': 27017,
       'db': 'smartshark',
       'username': '',
       'password': '',
       'authentication_source': 'smartshark',
       'connect': False}
connect(**loc)


def main():
    PROJECTS = ['ant-ivy', 'archiva', 'calcite', 'cayenne', 'commons-bcel', 'commons-beanutils',
                'commons-codec', 'commons-collections', 'commons-compress', 'commons-configuration',
                'commons-dbcp', 'commons-digester', 'commons-io', 'commons-jcs', 'commons-jexl',
                'commons-lang', 'commons-math', 'commons-net', 'commons-scxml',
                'commons-validator', 'commons-vfs', 'deltaspike', 'eagle', 'giraph', 'gora', 'jspwiki',
                'knox', 'kylin', 'lens', 'mahout', 'manifoldcf', 'nutch', 'opennlp', 'parquet-mr',
                'santuario-java', 'systemml', 'tika', 'wss4j']

    for project_name in PROJECTS:
        start = timeit.default_timer()
        print(project_name, end=' ')

        project = Project.objects.get(name=project_name)
        vcs_system = VCSSystem.objects.get(project_id=project.id)

        # fetch file
        repository = vcs_system.repository_file

        if repository.grid_id is None:
            raise Exception('no repository file for project!')

        fname = '../repos/{}.tar.gz'.format(project_name)

        # extract from gridfs
        with open(fname, 'wb') as f:
            f.write(repository.read())

        # extract tarfile
        with tarfile.open(fname, "r:gz") as tar_gz:
            tar_gz.extractall('../repos')

        # remove tarfile
        os.remove(fname)

        end = timeit.default_timer() - start
        print('finished in {:.5f}'.format(end))


if __name__ == '__main__':
    main()
