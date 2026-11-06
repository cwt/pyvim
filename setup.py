#!/usr/bin/env python
import os

from setuptools import find_packages, setup

import pyvim

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
    long_description = f.read()


setup(
    name='pyvim',
    author='Jonathan Slenders',
    version=pyvim.__version__,
    license='BSD License',
    url='https://github.com/jonathanslenders/pyvim',
    description='Pure Python Vi Implementation',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    packages=find_packages('.'),
    python_requires='>=3.10',
    install_requires=[
        'prompt_toolkit>=3.0.0,<3.1.0',
        'pyflakes',  # For Python error reporting.
        'pygments',  # For the syntax highlighting.
        'docopt',  # For command line arguments.
    ],
    entry_points={
        'console_scripts': [
            'pyvim = pyvim.entry_points.run_pyvim:run',
        ]
    },
)
