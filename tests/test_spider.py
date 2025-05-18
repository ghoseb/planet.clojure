#!/usr/bin/env python3

import os
import sys
import unittest
import logging
import feedparser
from xml.dom import minidom

import planet
from planet import config, spider

class SpiderTestCase(unittest.TestCase):
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

    def test_spider_feed(self):
        """Test spidering a single feed"""
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

        # Spider the feed
        spider.spiderFeed(feed_file)

        # Check that the feed was processed
        self.assertTrue(os.path.exists(os.path.join(self.cache_dir, 'test-entry-1.xml')))

    def test_spider_planet(self):
        """Test spidering all feeds"""
        # Create test feeds
        feeds = []
        for i in range(3):
            feed = minidom.parseString(f'''<?xml version="1.0" encoding="utf-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                    <title>Test Feed {i}</title>
                    <entry>
                        <title>Test Entry {i}</title>
                        <id>test-entry-{i}</id>
                    </entry>
                </feed>''')
            
            feed_file = os.path.join(self.cache_dir, f'test_feed_{i}.xml')
            with open(feed_file, 'w', encoding='utf-8') as f:
                f.write(feed.toxml())
            feeds.append(feed_file)

        # Spider all feeds
        spider.spiderPlanet()

        # Check that all feeds were processed
        for i in range(3):
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, f'test-entry-{i}.xml')))

    def test_spider_feeds(self):
        """Test spidering multiple feeds in parallel"""
        # Create test feeds
        feeds = []
        for i in range(3):
            feed = minidom.parseString(f'''<?xml version="1.0" encoding="utf-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                    <title>Test Feed {i}</title>
                    <entry>
                        <title>Test Entry {i}</title>
                        <id>test-entry-{i}</id>
                    </entry>
                </feed>''')
            
            feed_file = os.path.join(self.cache_dir, f'test_feed_{i}.xml')
            with open(feed_file, 'w', encoding='utf-8') as f:
                f.write(feed.toxml())
            feeds.append(feed_file)

        # Spider feeds in parallel
        spider.spiderFeeds()

        # Check that all feeds were processed
        for i in range(3):
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, f'test-entry-{i}.xml')))

if __name__ == '__main__':
    unittest.main()
