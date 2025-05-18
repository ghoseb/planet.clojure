from glob import glob
import os
import sys
import logging
import dbm
import pickle
import planet
from planet import config

if __name__ == '__main__':
    rootdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, rootdir)

from planet.spider import filename
from planet import logger as log

def filename(id):
    """Generate a filename for an ID"""
    return os.path.join(config.cache_directory(), id + '.db')

def open():
    try:
        cache = config.cache_directory()
        index = os.path.join(cache, 'index')
        if not os.path.exists(index):
            return None
        return dbm.open(filename(cache, 'id'), 'w')
    except Exception as e:
        if e.__class__.__name__ == 'DBError':
            e = e.args[-1]
        log.error(str(e))

def destroy():
    cache = config.cache_directory()
    index = os.path.join(cache, 'index')
    if not os.path.exists(index):
        return None
    idindex = filename(cache, 'id')
    if os.path.exists(idindex):
        os.unlink(idindex)
    os.removedirs(index)
    log.info(idindex + " deleted")

def create():
    """Create an index of feed entries"""
    cache_dir = config.cache_directory()
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    index_file = os.path.join(cache_dir, 'idindex.db')
    with dbm.open(index_file, 'c') as db:
        for feed in config.parser.sections():
            if feed.startswith('Feed '):
                feed_file = os.path.join(cache_dir, feed.replace(' ', '_') + '.xml')
                if os.path.exists(feed_file):
                    with open(feed_file, 'r', encoding='utf-8') as f:
                        data = f.read()
                        for entry in data.split('<entry>'):
                            if 'id>' in entry:
                                id = entry.split('id>')[1].split('<')[0]
                                db[id] = pickle.dumps(entry)
    logging.info("Created index with %d entries", len(dbm.open(index_file, 'r')))

def lookup(id):
    """Look up an entry by ID"""
    index_file = os.path.join(config.cache_directory(), 'idindex.db')
    if os.path.exists(index_file):
        with dbm.open(index_file, 'r') as db:
            if id in db:
                return pickle.loads(db[id])
    return None

def add(id, entry):
    """Add an entry to the index"""
    index_file = os.path.join(config.cache_directory(), 'idindex.db')
    with dbm.open(index_file, 'c') as db:
        db[id] = pickle.dumps(entry)

def remove(id):
    """Remove an entry from the index"""
    index_file = os.path.join(config.cache_directory(), 'idindex.db')
    if os.path.exists(index_file):
        with dbm.open(index_file, 'w') as db:
            if id in db:
                del db[id]

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: %s [-c|-d]' % sys.argv[0])
        sys.exit(1)

    config.load(sys.argv[1])

    if len(sys.argv) > 2 and sys.argv[2] == '-c':
        create()
    elif len(sys.argv) > 2 and sys.argv[2] == '-d':
        destroy()
    else:
        index = open()
        if index:
            log.info(str(len(list(index.keys()))) + " entries indexed")
            index.close()
        else:
            log.info("no entries indexed")
