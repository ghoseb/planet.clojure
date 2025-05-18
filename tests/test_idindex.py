#!/usr/bin/env python3

import os
import sys
import unittest
import logging
import pickle
from xml.dom import minidom

import planet
from planet import config, idindex

class IdIndexTestCase(unittest.TestCase):
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

    def test_create_index(self):
        """Test creating an index"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Create the index
        idindex.create()

        # Check that the index was created
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, 'test-entry-1.db')))

    def test_lookup_entry(self):
        """Test looking up an entry"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Create the index
        idindex.create()

        # Look up the entry
        entry = idindex.lookup('test-entry-1')
        self.assertIsNotNone(entry)
        self.assertEqual(entry.title, 'Test Entry')

    def test_add_entry(self):
        """Test adding an entry"""
        # Create a test entry
        entry = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <entry xmlns="http://www.w3.org/2005/Atom">
                <title>Test Entry</title>
                <id>test-entry-1</id>
            </entry>''').documentElement

        # Add the entry
        idindex.add('test-entry-1', entry)

        # Check that the entry was added
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, 'test-entry-1.db')))

    def test_remove_entry(self):
        """Test removing an entry"""
        # Create a test entry
        entry = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <entry xmlns="http://www.w3.org/2005/Atom">
                <title>Test Entry</title>
                <id>test-entry-1</id>
            </entry>''').documentElement

        # Add the entry
        idindex.add('test-entry-1', entry)

        # Remove the entry
        idindex.remove('test-entry-1')

        # Check that the entry was removed
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, 'test-entry-1.db')))

if __name__ == '__main__':
    unittest.main()
