#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, opml

class OpmlTestCase(unittest.TestCase):
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

    def test_parse_opml(self):
        """Test parsing an OPML file"""
        # Create a test OPML file
        opml_data = '''<?xml version="1.0" encoding="utf-8"?>
            <opml version="1.0">
                <head>
                    <title>Test OPML</title>
                </head>
                <body>
                    <outline text="Test Feed" xmlUrl="http://example.com/feed"/>
                </body>
            </opml>'''
        
        opml_file = os.path.join(self.cache_dir, 'test_opml.xml')
        with open(opml_file, 'w', encoding='utf-8') as f:
            f.write(opml_data)

        # Parse the OPML file
        feeds = opml.parse_opml(opml_file)

        # Check that the feeds were parsed correctly
        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0], 'http://example.com/feed')

    def test_parse_opml_with_multiple_feeds(self):
        """Test parsing an OPML file with multiple feeds"""
        # Create a test OPML file
        opml_data = '''<?xml version="1.0" encoding="utf-8"?>
            <opml version="1.0">
                <head>
                    <title>Test OPML</title>
                </head>
                <body>
                    <outline text="Test Feed 1" xmlUrl="http://example.com/feed1"/>
                    <outline text="Test Feed 2" xmlUrl="http://example.com/feed2"/>
                </body>
            </opml>'''
        
        opml_file = os.path.join(self.cache_dir, 'test_opml.xml')
        with open(opml_file, 'w', encoding='utf-8') as f:
            f.write(opml_data)

        # Parse the OPML file
        feeds = opml.parse_opml(opml_file)

        # Check that the feeds were parsed correctly
        self.assertEqual(len(feeds), 2)
        self.assertIn('http://example.com/feed1', feeds)
        self.assertIn('http://example.com/feed2', feeds)

    def test_parse_opml_with_nested_feeds(self):
        """Test parsing an OPML file with nested feeds"""
        # Create a test OPML file
        opml_data = '''<?xml version="1.0" encoding="utf-8"?>
            <opml version="1.0">
                <head>
                    <title>Test OPML</title>
                </head>
                <body>
                    <outline text="Category 1">
                        <outline text="Test Feed 1" xmlUrl="http://example.com/feed1"/>
                    </outline>
                    <outline text="Category 2">
                        <outline text="Test Feed 2" xmlUrl="http://example.com/feed2"/>
                    </outline>
                </body>
            </opml>'''
        
        opml_file = os.path.join(self.cache_dir, 'test_opml.xml')
        with open(opml_file, 'w', encoding='utf-8') as f:
            f.write(opml_data)

        # Parse the OPML file
        feeds = opml.parse_opml(opml_file)

        # Check that the feeds were parsed correctly
        self.assertEqual(len(feeds), 2)
        self.assertIn('http://example.com/feed1', feeds)
        self.assertIn('http://example.com/feed2', feeds)

    def test_parse_opml_with_invalid_xml(self):
        """Test parsing an invalid OPML file"""
        # Create an invalid OPML file
        opml_data = '''<?xml version="1.0" encoding="utf-8"?>
            <opml version="1.0">
                <head>
                    <title>Test OPML</title>
                </head>
                <body>
                    <outline text="Test Feed" xmlUrl="http://example.com/feed"/>
                </body>
            </opml'''
        
        opml_file = os.path.join(self.cache_dir, 'test_opml.xml')
        with open(opml_file, 'w', encoding='utf-8') as f:
            f.write(opml_data)

        # Parse the OPML file
        feeds = opml.parse_opml(opml_file)

        # Check that no feeds were parsed
        self.assertEqual(len(feeds), 0)

if __name__ == '__main__':
    unittest.main()
