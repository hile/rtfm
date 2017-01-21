
import glob

from setuptools import setup, find_packages
from rtfm import __version__

setup(
    name = 'rtfm',
    keywords = 'Documentation Mirroring tools',
    description = 'Script to mirror and search RFCs cache',
    author = 'Ilkka Tuohela',
    author_email = 'hile@iki.fi',
    url = 'https://github.com/hile/rtfm/',
    version = __version__,
    license = 'PSF',
    packages = find_packages(),
    scripts = glob.glob('bin/*'),
    install_requires = (
        'systematic',
        'whoosh',
    )
)

