# :coding: utf-8
# :copyright: Copyright (c) 2014 ftrack

import os
import re
import glob

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


ROOT_PATH = os.path.dirname(os.path.realpath(__file__))
RESOURCE_PATH = os.path.join(ROOT_PATH, 'resource')
SOURCE_PATH = os.path.join(ROOT_PATH, 'source')
README_PATH = os.path.join(ROOT_PATH, 'README.rst')


# Read version from source.
with open(os.path.join(SOURCE_PATH, 'ftrack', '_version.py')) as _version_file:
    VERSION = re.match(
        r'.*__version__ = \'(.*?)\'', _version_file.read(), re.DOTALL
    ).group(1)


# Custom commands.
class PyTest(TestCommand):
    '''Pytest command.'''

    def finalize_options(self):
        '''Finalize options to be used.'''
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        '''Import pytest and run.'''
        import pytest
        raise SystemExit(pytest.main(self.test_args))


# Call main setup.
setup(
    name='ftrack-python-api',
    version=VERSION,
    description='Python API for ftrack.',
    long_description=open(README_PATH).read(),
    keywords='ftrack, python, api',
    url='https://bitbucket.org/ftrack/ftrack-python-api',
    author='ftrack',
    author_email='support@ftrack.com',
    license='Apache License (2.0)',
    packages=find_packages(SOURCE_PATH),
    package_dir={
        '': 'source'
    },
    setup_requires=[
        'sphinx >= 1.2.2, < 2',
        'sphinx_rtd_theme >= 0.1.6, < 1'
    ],
    install_requires=[
        'requests >= 2, <3',
        'arrow >= 0.4.4, < 1',
        'termcolor >= 1.1.0, < 2',
        'pyparsing >= 2.0, < 3',
        'clique >= 1.2.0, < 2',
        'websocket-client == 0.12'
    ],
    tests_require=[
        'pytest >= 2.3.5, < 3'
    ],
    cmdclass={
        'test': PyTest
    },
    data_files=[
        (
            'ftrack_default_plugins',
            glob.glob(os.path.join(RESOURCE_PATH, 'plugin', '*.py'))
        )
    ],
    zip_safe=False
)
