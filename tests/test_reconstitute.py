#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, reconstitute

class ReconstituteTestCase(unittest.TestCase):
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

    def test_reconstitute_feed(self):
        """Test reconstituting a feed"""
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

        # Save individual entries
        entry_file = os.path.join(self.cache_dir, 'test-entry-1.xml')
        with open(entry_file, 'w', encoding='utf-8') as f:
            f.write(feed.getElementsByTagName('entry')[0].toxml())

        # Reconstitute the feed
        reconstitute.reconstitute_feed(feed_file)

        # Check that the feed was reconstituted
        with open(feed_file, 'r', encoding='utf-8') as f:
            reconstituted_feed = minidom.parseString(f.read())
        self.assertEqual(len(reconstituted_feed.getElementsByTagName('entry')), 1)
        self.assertEqual(reconstituted_feed.getElementsByTagName('entry')[0].getElementsByTagName('title')[0].firstChild.nodeValue, 'Test Entry')

    def test_reconstitute_feed_with_multiple_entries(self):
        """Test reconstituting a feed with multiple entries"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry 1</title>
                    <id>test-entry-1</id>
                    <content type="text">Test content 1</content>
                </entry>
                <entry>
                    <title>Test Entry 2</title>
                    <id>test-entry-2</id>
                    <content type="text">Test content 2</content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Save individual entries
        for entry in feed.getElementsByTagName('entry'):
            entry_id = entry.getElementsByTagName('id')[0].firstChild.nodeValue
            entry_file = os.path.join(self.cache_dir, f'{entry_id}.xml')
            with open(entry_file, 'w', encoding='utf-8') as f:
                f.write(entry.toxml())

        # Reconstitute the feed
        reconstitute.reconstitute_feed(feed_file)

        # Check that the feed was reconstituted
        with open(feed_file, 'r', encoding='utf-8') as f:
            reconstituted_feed = minidom.parseString(f.read())
        self.assertEqual(len(reconstituted_feed.getElementsByTagName('entry')), 2)
        titles = [entry.getElementsByTagName('title')[0].firstChild.nodeValue 
                 for entry in reconstituted_feed.getElementsByTagName('entry')]
        self.assertIn('Test Entry 1', titles)
        self.assertIn('Test Entry 2', titles)

    def test_reconstitute_feed_with_missing_entry(self):
        """Test reconstituting a feed with a missing entry"""
        # Create a test feed
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry 1</title>
                    <id>test-entry-1</id>
                    <content type="text">Test content 1</content>
                </entry>
                <entry>
                    <title>Test Entry 2</title>
                    <id>test-entry-2</id>
                    <content type="text">Test content 2</content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Save only one entry
        entry = feed.getElementsByTagName('entry')[0]
        entry_id = entry.getElementsByTagName('id')[0].firstChild.nodeValue
        entry_file = os.path.join(self.cache_dir, f'{entry_id}.xml')
        with open(entry_file, 'w', encoding='utf-8') as f:
            f.write(entry.toxml())

        # Reconstitute the feed
        reconstitute.reconstitute_feed(feed_file)

        # Check that the feed was reconstituted with only the available entry
        with open(feed_file, 'r', encoding='utf-8') as f:
            reconstituted_feed = minidom.parseString(f.read())
        self.assertEqual(len(reconstituted_feed.getElementsByTagName('entry')), 1)
        self.assertEqual(reconstituted_feed.getElementsByTagName('entry')[0].getElementsByTagName('title')[0].firstChild.nodeValue, 'Test Entry 1')

if __name__ == '__main__':
    unittest.main()
