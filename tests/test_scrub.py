#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, scrub

class ScrubTestCase(unittest.TestCase):
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

    def test_scrub_html(self):
        """Test scrubbing HTML content"""
        # Create a test feed with HTML content
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                    <content type="html">
                        <![CDATA[
                        <p>Test content with <script>alert("XSS")</script> and <style>body { color: red; }</style></p>
                        ]]>
                    </content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Scrub the feed
        scrub.scrub_feed(feed_file)

        # Check that the feed was scrubbed
        with open(feed_file, 'r', encoding='utf-8') as f:
            scrubbed_feed = minidom.parseString(f.read())
        content = scrubbed_feed.getElementsByTagName('content')[0].firstChild.nodeValue
        self.assertNotIn('<script>', content)
        self.assertNotIn('<style>', content)
        self.assertIn('<p>', content)

    def test_scrub_xhtml(self):
        """Test scrubbing XHTML content"""
        # Create a test feed with XHTML content
        feed = minidom.parseString('''<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
                <title>Test Feed</title>
                <entry>
                    <title>Test Entry</title>
                    <id>test-entry-1</id>
                    <content type="xhtml">
                        <div xmlns="http://www.w3.org/1999/xhtml">
                            <p>Test content with <script>alert("XSS")</script> and <style>body { color: red; }</style></p>
                        </div>
                    </content>
                </entry>
            </feed>''')
        
        # Save the feed
        feed_file = os.path.join(self.cache_dir, 'test_feed.xml')
        with open(feed_file, 'w', encoding='utf-8') as f:
            f.write(feed.toxml())

        # Scrub the feed
        scrub.scrub_feed(feed_file)

        # Check that the feed was scrubbed
        with open(feed_file, 'r', encoding='utf-8') as f:
            scrubbed_feed = minidom.parseString(f.read())
        content = scrubbed_feed.getElementsByTagName('content')[0].firstChild.nodeValue
        self.assertNotIn('<script>', content)
        self.assertNotIn('<style>', content)
        self.assertIn('<p>', content)

    def test_scrub_text(self):
        """Test scrubbing text content"""
        # Create a test feed with text content
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

        # Scrub the feed
        scrub.scrub_feed(feed_file)

        # Check that the feed was not modified
        with open(feed_file, 'r', encoding='utf-8') as f:
            scrubbed_feed = minidom.parseString(f.read())
        content = scrubbed_feed.getElementsByTagName('content')[0].firstChild.nodeValue
        self.assertEqual(content, 'Test content')

if __name__ == '__main__':
    unittest.main()
