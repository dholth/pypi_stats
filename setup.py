import os, codecs

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
README = codecs.open(os.path.join(here, 'README.txt'), encoding='utf8').read()
CHANGES = codecs.open(os.path.join(here, 'CHANGES.txt'), encoding='utf8').read()

setup(name='pypi_stats',
      version='0.0.1',
      description='Parse metadata out of the sdists in a local pypi mirror.',
      long_description=README + '\n\n' +  CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7"
        ],
      author='Daniel Holth',
      author_email='dholth@gmail.com',
      url='http://bitbucket.org/dholth/pypi_stats/',
      keywords='pypi cheeseshop sdist',
      license='MIT',
      packages = [ 'pypi_stats' ],
      install_requires = [ 'wheel', 'SQLAlchemy' ],
      include_package_data=True,
      zip_safe=False,
      test_suite = 'nose.collector',
      )

