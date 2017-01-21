#!/usr/bin/env python
"""
Classes to parse and update the RFC index file and local copies of
RFC text files.
"""

import os
import re
import sys
import requests

from configobj import ConfigObj, Section, ConfigObjError
from datetime import datetime
from systematic.log import Logger, LoggerError

import whoosh.index as windex
from whoosh.qparser import QueryParser
from whoosh.fields import Schema, TEXT, NUMERIC, ID
from whoosh.writing import IndexingError

# Defaults for cache directories and filenames
RFC_DEFAULT_CACHE_DIR = '~/.cache/rtfm'
INDEX_FILENAME = 'rfc-index.txt'

# URLs for fetching files
INDEX_URL = 'http://www.ietf.org/download/rfc-index.txt'
RFC_BASE_URL = 'http://www.ietf.org/rfc/'

# Following RFCs are not relevant and give 403 from ietf.org site
RFC_SKIPPED = ( 8, 9, 51, 418, 530, 598 )

# Whoosh schema for RFC caches
RFC_CACHE_SCHEMA = Schema(
    number=NUMERIC(unique=True, stored=True),
    title=TEXT(stored=True),
    content=TEXT
)

RE_RFC_INDEX_LINE = re.compile('^(\d+)\s*(.+)$')
RE_RFC_DESCRIPTION = re.compile('^(?P<title>.*\.) (?P<date>[A-Z][a-z]+ \d+)\. (?P<flags>\(.*\))$')

CACHE_COMMIT_INTERVAL = 50

class RFCCacheError(Exception):
    pass


class RFCCacheEntry(object):
    """RFC cache entry

    Cache entry for a single RFC, linking rfc to local file
    """

    def __init__(self, cache, number, description):
        self.log = Logger('rtfm').default_stream
        self.cache = cache
        self.number = int(number)

        self.title = 'title not parsed'
        self.authors = []
        self.flags = {}

        self.description = description.decode('utf-8')
        m = RE_RFC_DESCRIPTION.match(self.description)
        if m:
            self.title = m.groupdict()['title']
            self.date = datetime.strptime(m.groupdict()['date'], '%B %Y').date()
            self.flags = self.__parse_flags__(m.groupdict()['flags'])

    def __int__(self):
        return self.number

    def __eq__(self, other):
        return self.number == other.number

    def __ne__(self, other):
        return self.number != other.number

    def __lt__(self, other):
        return self.number < other.number

    def __le__(self, other):
        return self.number <= other.number

    def __gt__(self, other):
        return self.number > other.number

    def __ge__(self, other):
        return self.number >= other.number

    def __repr__(self):
        return self.title

    def __parse_flags__(self, value):
        """Parse flags

        """
        flags = {}
        for v in [v.lstrip(' (') for v in value.strip().split(')')]:
            if v.strip() == '':
                continue
            try:
                key, value = [x.strip() for x in v.split(':', 1)]
                flags[key] = value
            except ValueError:
                pass
        return flags

    @property
    def path(self):
        """Full path to RFC

        """
        return os.path.join(self.cache.cachedir, 'files', self.filename).decode('utf-8')

    @property
    def filename(self):
        """Filename for RFC

        Filename for cache entry in RFC cache directory
        """
        return 'rfc{0}.txt'.format(self.number)

    @property
    def exists(self):
        """Check if local file exists

        """
        return os.path.isfile(self.path)

    @property
    def rfc_download_url(self):
        """URL to download RFC

        """
        return '{0}rfc{1:04d}.txt'.format(RFC_BASE_URL, self.number)

    def update(self):
        """Update RFC

        Update the RFC text file from web
        """
        rfc_directory = os.path.dirname(self.path)
        if not os.path.isdir(rfc_directory):
            try:
                os.makedirs(rfc_directory)
            except IOError as e:
                raise RFCCacheError('Error creating directory {0}: {1}'.format(rfc_directory, e))
            except OSError as e:
                raise RFCCacheError('Error creating directory {0}: {1}'.format(rfc_directory, e))

        self.log.debug('Downloading RFC: {0}'.format(self.rfc_download_url))
        res = requests.get(self.rfc_download_url)
        if res.status_code != 200:
            raise RFCCacheError('Error downloading {0}: status code {1}'.format(self.rfc_download_url, res.status_code))

        try:
            open(self.path, 'w').write(res.content)
        except IOError as e:
            raise RFCCacheError('Error writing {0}: {1}'.format(self.path, e))
        except OSError as e:
            raise RFCCacheError('Error writing {0}: {1}'.format(self.path, e))


class RFCIndex(list):
    """RFC cache index

    """
    def __init__(self, cachedir=RFC_DEFAULT_CACHE_DIR):
        self.log = Logger('rtfm').default_stream

        self.cachedir = os.path.expanduser(os.path.expandvars(cachedir))
        self.windex_path = os.path.join(self.cachedir, 'index')

        for path in ( self.cachedir, self.windex_path ):
            if not os.path.isdir(path):
                try:
                    os.makedirs(path)
                except Exception as e:
                    raise RFCCacheError('Error creating directory {0}: {1}'.format(path, e))

        if windex.exists_in(self.windex_path):
            self.windex = windex.open_dir(self.windex_path)
        else:
            self.log.debug('Create new whoosh index to {0}'.format(self.windex_path))
            self.windex = windex.create_in(self.windex_path, RFC_CACHE_SCHEMA)

        if os.path.isfile(self.path):
            self.load()

    @property
    def path(self):
        """RFC cache file path

        """
        return os.path.join(self.cachedir, INDEX_FILENAME)

    def load(self):
        """Load RFC index

        Load local RFC index file
        """

        if not os.path.isfile(self.path):
            raise RFCCacheError('Error loading {0}: no such file'.format(self.path))

        del self[0:len(self)]

        try:

            with open(self.path, 'r') as f:

                header = False
                rfc = None
                text = None

                for line in f:
                    line = line.rstrip()
                    if line == '':
                        continue

                    # Parse any header text out
                    if line.startswith('~~~'):
                        if not header:
                            header = True
                            continue
                        else:
                            header = False
                            continue

                    if header or line.strip() in ( 'RFC INDEX', '---------' ):
                        continue

                    m = re.match(RE_RFC_INDEX_LINE, line)
                    if m:
                        if rfc is not None and rfc not in RFC_SKIPPED:
                            try:
                                self.append(RFCCacheEntry(self, rfc, text))
                            except RFCCacheError:
                                pass
                        rfc = int(m.group(1))
                        text = m.group(2)
                        if text == 'Not Issued.':
                            rfc = None
                            text = None

                    else:
                        if not rfc:
                            raise RFCCacheError('Unsupported file format.')

                        text = '{0} {1}'.format(text, line.strip())

        except IOError as e:
            raise RFCCacheError('Error loading RFC cache {0}: {1}'.format(self.path, e))
        except OSError as e:
            raise RFCCacheError('Error loading RFC cache {0}: {1}'.format(self.path, e))

    def update(self):
        """Update RFC index

        Update the RFC index text file from web
        """

        res = requests.get(INDEX_URL)
        if res.status_code != 200:
            raise RFCCacheError('Error downloading {0}: status code {1}'.format(INDEX_URL, res.status_code))

        try:
            open(self.path, 'w').write(res.content)
        except OSError as e:
            raise RFCCacheError('Error writing {0}: {1}'.format(self.path,e))

        self.load()

    def get_indexed(self):
        """Get indexed RFCs

        Return RFC numbders for RFCs in whoosh search index
        """
        return sorted([f['number'] for f in self.windex.searcher().all_stored_fields()])

    def get_by_number(self, number):
        """Find RFC by number

        Return given RFC entry, raise RFCCacheError if not found.
        """
        if len(self) == 0:
            raise RFCCacheError('No RFCs loaded to index')

        try:
            number = int(number)
            if number < 1:
                raise ValueError
        except ValueError:
            raise RFCCacheError('Invalid RFC number: {0}'.format(number))
        except TypeError:
            raise RFCCacheError('Invalid RFC number: {0}'.format(number))

        if number in RFC_SKIPPED:
            raise RFCCacheError('RFC {0:04d} not available from web (obsolete?)'.format(number))

        if number > self[-1].number:
            raise RFCCacheError('Requested {0:04d}, latest cached RFC {1:04d}'.format(number, self[-1].number))

        for rfc in self:
            if rfc.number == number:
                return rfc

        raise RFCCacheError('RFC {0:04d} not found from local cache'.format(number))

    def update_missing_indexes(self):
        """Index missing entries

        """

        indexed = self.get_indexed()
        writer = self.windex.writer()
        done = 0

        for rfc in [rfc for rfc in self if rfc.number not in indexed]:

            self.log.debug('Create index: RFC {0}'.format(rfc.number))

            try:
                data = open(rfc.path, 'r').read()
            except OSError as e:
                raise RFCCacheError('Error reading {0}: {1}'.format(rfc.path, e))
            except IOError as e:
                raise RFCCacheError('Error reading {0}: {1}'.format(rfc.path, e))

            try:
                document = data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    document= data.decode('iso-8859-1')
                except UnicodeDecodeError:
                    raise RFCCacheError('RFC {0}: unknonwn file charset'.format(rfc.number))

            writer.update_document(
                number=rfc.number,
                title=rfc.description,
                content=document
            )

            # Commit every now and then
            if done >= CACHE_COMMIT_INTERVAL:
                writer.commit()
                writer = self.windex.writer()
                done = 0
            else:
                done += 1

        try:
            writer.commit()
        except IndexingError:
            pass

    def search(self, terms, bodysearch=False):
        """Search RFC term cache

        Search the RFC descriptions matching given regexp

        If 'bodysearch' is True, search the body of cached RFC files as well
        """
        terms = ' '.join(term.lower() for term in terms)
        s = self.windex.searcher()

        rfcs = []
        results = []

        title_matches = s.search(QueryParser("title", RFC_CACHE_SCHEMA).parse(terms))
        for r in title_matches:
            rfcs.append(r['number'])
            results.append(self.get_by_number(r['number']))

        if bodysearch:
            body_matches = s.search(QueryParser("content", RFC_CACHE_SCHEMA).parse(terms))
            for r in body_matches:
                if r['number'] in rfcs:
                    continue
                rfcs.append(r['number'])
                results.append(self.get_by_number(r['number']))

        results.sort()
        return results

