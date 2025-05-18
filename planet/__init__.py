xmlns = 'http://planet.intertwingly.net/'

logger = None
loggerParms = None

import os
import sys
import re
import logging
from configparser import ConfigParser
from urllib.parse import urljoin

def getLogger(level, format):
    """Get a logger with the specified log level"""
    global logger, loggerParms
    if logger and loggerParms == (level, format):
        return logger

    try:
        import logging
        logging.basicConfig(format=format)
    except ImportError:
        import compat_logging as logging
        logging.basicConfig(format=format)

    logger = logging.getLogger("planet.runner")
    logger.setLevel(logging.getLevelName(level))
    try:
        logger.warning
    except AttributeError:
        logger.warning = logger.warn

    loggerParms = (level, format)
    return logger

sys.path.insert(1, os.path.join(os.path.dirname(__file__), 'vendor'))

# Configure feed parser
import feedparser
feedparser.SANITIZE_HTML = 1
feedparser.RESOLVE_RELATIVE_URIS = 0

import publish
