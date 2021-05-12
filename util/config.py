"""Config object for shared configuration information and utility functions."""

import os
from pycoshark.utils import java_filename_filter


class Config():
    """Config object shared for all of Gierlappen."""

    def __init__(self, args):
        # self.__dict__.update(args.__dict__)

        self.project = args.project
        self.path = args.path
        self.production_only = args.production_only
        self.labels = getattr(args, 'labels', [])
        self.language = args.language
        self.keywords = args.keywords
        self.to_date = args.to_date
        self.is_test = args.is_test

        # smartshark db info, they are optional
        self.db_host = getattr(args, 'db_host', '')
        self.db_port = getattr(args, 'db_port', '')
        self.db_name = getattr(args, 'db_name', '')
        self.db_user = getattr(args, 'db_user', '')
        self.db_pw = getattr(args, 'db_pw', '')
        self.db_auth = getattr(args, 'db_auth', '')

        self.pg_host = getattr(args, 'pg_host', '')
        self.pg_port = getattr(args, 'pg_port', '')
        self.pg_name = getattr(args, 'pg_name', '')
        self.pg_user = getattr(args, 'pg_user', '')
        self.pg_pw = getattr(args, 'pg_pw', '')
        self.pg_schema = getattr(args, 'pg_schema', '')

        self.file_check = args.file_check

        # connectors
        self.use_maven = args.use_maven
        self.connector = args.connector  # smartshark
        self.use_linter = args.use_linter

        # if we use pmd the path is always this
        self.pmd_path = os.path.abspath('./checks/pmd/')

        self.quality_keywords = args.quality_keywords


        self.set_extensions(args.language)

    def set_extensions(self, language):
        if language == 'java':
            self.extensions = [".java"]  # ".pm"
        elif language == 'python':
            self.extensions = ['.py']
        else:
            raise Exception('no extension for language')

    def python_filename_filter(self, filename, production_only=True):
        """Relocate this later to pycoshark"""

        # not even .py, out of here!
        if not filename.lower().endswith('.py'):
            return False

        # we are python, no further restriction
        if not production_only:
            return True

        # production_only is true here
        if '/test/' in filename or '/tests/' in filename:
            return False

        # everyone else jump out
        return True

    def filename_filter(self, filename):
        if self.language == 'java':
            return java_filename_filter(filename, production_only=self.production_only)
        if self.language == 'python':
            return self.python_filename_filter(filename, production_only=self.production_only)
