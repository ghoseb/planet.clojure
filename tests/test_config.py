#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from configparser import ConfigParser

import planet
from planet import config

class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.config = os.path.join(os.path.dirname(__file__), 'data', 'test.ini')
        config.load(self.config)

    def test_basic_config(self):
        """Test basic configuration loading"""
        self.assertEqual(config.name(), "Test Planet")
        self.assertEqual(config.link(), "http://example.com")
        self.assertEqual(config.cache_directory(), "cache")
        self.assertEqual(config.output_dir(), "output")

    def test_template_config(self):
        """Test template configuration"""
        self.assertEqual(config.template_files(), ["index.html.tmpl", "atom.xml.tmpl"])
        self.assertEqual(config.template_directories(), ["."])
        self.assertEqual(config.bill_of_materials(), ["style.css"])

    def test_feed_config(self):
        """Test feed configuration"""
        feeds = config.subscriptions()
        self.assertTrue(len(feeds) > 0)
        self.assertTrue(any(feed.startswith('Feed ') for feed in feeds))

    def test_filter_config(self):
        """Test filter configuration"""
        self.assertEqual(config.filters(), [])
        config.parser.set('Planet', 'filters', 'regexp_sifter.py?require=Test')
        self.assertEqual(config.filters(), ['regexp_sifter.py?require=Test'])

    def test_twitter_config(self):
        """Test Twitter configuration"""
        self.assertFalse(config.post_to_twitter())
        config.parser.set('Planet', 'post_to_twitter', 'true')
        self.assertTrue(config.post_to_twitter())

if __name__ == '__main__':
    unittest.main()


