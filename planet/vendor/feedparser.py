#!/usr/bin/env python3

import os
import sys
import logging
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from xml.dom import minidom
from io import StringIO

class FeedParser:
    def __init__(self, url=None, data=None, encoding=None):
        self.url = url
        self.data = data
        self.encoding = encoding
        self.feed = None
        self.entries = []
        
    def parse(self):
        """Parse a feed from a URL or data string."""
        if self.url:
            try:
                with urllib.request.urlopen(self.url) as response:
                    self.data = response.read()
                    if self.encoding:
                        self.data = self.data.decode(self.encoding)
                    else:
                        self.data = self.data.decode('utf-8')
            except urllib.error.URLError as e:
                logging.error(f"Failed to fetch feed from {self.url}: {e}")
                raise
                
        if not self.data:
            raise ValueError("No feed data provided")
            
        # Parse the feed
        try:
            doc = minidom.parseString(self.data)
        except Exception as e:
            logging.error(f"Failed to parse feed: {e}")
            raise
            
        # Extract feed information
        self.feed = self._parse_feed(doc)
        
        # Extract entries
        for entry in doc.getElementsByTagName('entry'):
            self.entries.append(self._parse_entry(entry))
            
        return self
        
    def _parse_feed(self, doc):
        """Parse feed-level information."""
        feed = {}
        
        # Get feed title
        title_elem = doc.getElementsByTagName('title')
        if title_elem:
            feed['title'] = title_elem[0].firstChild.nodeValue
            
        # Get feed link
        link_elem = doc.getElementsByTagName('link')
        if link_elem:
            feed['link'] = link_elem[0].getAttribute('href')
            
        # Get feed description
        desc_elem = doc.getElementsByTagName('description')
        if desc_elem:
            feed['description'] = desc_elem[0].firstChild.nodeValue
            
        return feed
        
    def _parse_entry(self, entry):
        """Parse an individual entry."""
        result = {}
        
        # Get entry title
        title_elem = entry.getElementsByTagName('title')
        if title_elem:
            result['title'] = title_elem[0].firstChild.nodeValue
            
        # Get entry link
        link_elem = entry.getElementsByTagName('link')
        if link_elem:
            result['link'] = link_elem[0].getAttribute('href')
            
        # Get entry content
        content_elem = entry.getElementsByTagName('content')
        if content_elem:
            result['content'] = content_elem[0].firstChild.nodeValue
            
        # Get entry published date
        published_elem = entry.getElementsByTagName('published')
        if published_elem:
            result['published'] = published_elem[0].firstChild.nodeValue
            
        return result

# ... existing code ...
