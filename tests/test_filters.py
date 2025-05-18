#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, filters

class FiltersTestCase(unittest.TestCase):
    def setUp(self):
        self.config = os.path.join(os.path.dirname(__file__), 'data', 'test.ini')
        config.load(self.config)
        self.cache_dir = config.cache_directory()
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def tearDown(self):
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                os.remove(os.path.join(self.cache_dir, file))
            os.rmdir(self.cache_dir)

    def test_apply_filters(self):
        """Test applying filters to a feed"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                    <content type="text">Test content</content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Create a test filter
        filter_code = '''
def filter(entry):
    entry.title = entry.title.upper()
    return entry
'''
        filter_file = os.path.join(self.cache_dir, 'test_filter.py')
        with open(filter_file, 'w', encoding='utf-8') as f:
            f.write(filter_code)

        # Apply the filter
        config.parser.set('Planet', 'filters', 'test_filter.py')
        filters.apply_filters(feed_file)

        # Check that the filter was applied
        with open(feed_file, 'r', encoding='utf-8') as f:
            filtered_feed = minidom.parseString(f.read())
        self.assertEqual(filtered_feed.getElementsByTagName('title')[0].firstChild.nodeValue, 'TEST ENTRY')

    def test_apply_multiple_filters(self):
        """Test applying multiple filters to a feed"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                    <content type="text">Test content</content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Create test filters
        filter1_code = '''
def filter(entry):
    entry.title = entry.title.upper()
    return entry
'''
        filter1_file = os.path.join(self.cache_dir, 'test_filter1.py')
        with open(filter1_file, 'w', encoding='utf-8') as f:
            f.write(filter1_code)

        filter2_code = '''
def filter(entry):
    entry.title = entry.title.lower()
    return entry
'''
        filter2_file = os.path.join(self.cache_dir, 'test_filter2.py')
        with open(filter2_file, 'w', encoding='utf-8') as f:
            f.write(filter2_code)

        # Apply the filters
        config.parser.set('Planet', 'filters', 'test_filter1.py,test_filter2.py')
        filters.apply_filters(feed_file)

        # Check that the filters were applied
        with open(feed_file, 'r', encoding='utf-8') as f:
            filtered_feed = minidom.parseString(f.read())
        self.assertEqual(filtered_feed.getElementsByTagName('title')[0].firstChild.nodeValue, 'test entry')

if __name__ == '__main__':
    unittest.main()
