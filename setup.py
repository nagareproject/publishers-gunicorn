# Encoding: utf-8

# --
# Copyright (c) 2008-2020 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

import os

from setuptools import setup, find_packages


here = os.path.normpath(os.path.dirname(__file__))

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as description:
    LONG_DESCRIPTION = description.read()


setup(
    name='nagare-publishers-gunicorn',
    author='Net-ng',
    author_email='alain.poirier@net-ng.com',
    description='Guicorn publisher',
    long_description=LONG_DESCRIPTION,
    license='BSD',
    keywords='',
    url='https://github.com/nagareproject/publishers-gunicorn',
    packages=find_packages(),
    zip_safe=False,
    setup_requires=['setuptools_scm'],
    use_scm_version=True,
    install_requires=[
        'futures; python_version == "2.7"',
        'ws4py',
        'gunicorn[gthread]',
        'nagare-server-http'
    ],
    entry_points='''
        [nagare.publishers]
        gunicorn = nagare.publishers.gunicorn_publisher:Publisher
    '''
)
