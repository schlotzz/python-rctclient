# -*- coding: utf-8 -*-
from setuptools import setup  # type: ignore

setup(
    name='rctclient',
    version='0.0.1',
    author='Peter Oberhofer',
    description='Implementation of the RCT Power communication protocol',
    project_urls={
        'Documentation': 'https://rctclient.readthedocs.org/',
        'Source': 'https://github.com/svalouch/rctclient/',
        'Tracker': 'https://github.com/svalouch/rctclient/issues',
    },
    packages=['rctclient'],
    package_data={'rctclient': ['py.typed']},
    package_dir={'': 'src'},
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    python_requires='>=3.6',

    # install_requires=[
    # ],

    extras_require={
        'cli': [
            'click',
        ],
        'dev': [
            'flake8',
            'mypy',
            'pytest',
        ],
        'docs': [
            'click',
            'Sphinx>=2.0',
            'sphinx-autodoc-typehints',
            'sphinx-click',
            'sphinx-rtd-theme',
        ],
    },
    entry_points={
        'console_scripts': [
            'rctclient=rctclient.cli:cli',
        ],
    },

    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)