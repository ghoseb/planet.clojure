#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, foaf

class FoafTestCase(unittest.TestCase):
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

    def test_parse_foaf(self):
        """Test parsing a FOAF file"""
        # Create a test FOAF file
        foaf_data = '''<?xml version="1.0" encoding="utf-8"?>
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                     xmlns:foaf="http://xmlns.com/foaf/0.1/">
                <foaf:Person>
                    <foaf:name>Test Person</foaf:name>
                    <foaf:weblog rdf:resource="http://example.com/blog"/>
                </foaf:Person>
            </rdf:RDF>'''
        
        foaf_file = os.path.join(self.cache_dir, 'test_foaf.rdf')
        with open(foaf_file, 'w', encoding='utf-8') as f:
            f.write(foaf_data)

        # Parse the FOAF file
        feeds = foaf.parse_foaf(foaf_file)

        # Check that the feeds were parsed correctly
        self.assertEqual(len(feeds), 1)
        self.assertEqual(feeds[0], 'http://example.com/blog')

    def test_parse_foaf_with_multiple_feeds(self):
        """Test parsing a FOAF file with multiple feeds"""
        # Create a test FOAF file
        foaf_data = '''<?xml version="1.0" encoding="utf-8"?>
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                     xmlns:foaf="http://xmlns.com/foaf/0.1/">
                <foaf:Person>
                    <foaf:name>Test Person 1</foaf:name>
                    <foaf:weblog rdf:resource="http://example.com/blog1"/>
                </foaf:Person>
                <foaf:Person>
                    <foaf:name>Test Person 2</foaf:name>
                    <foaf:weblog rdf:resource="http://example.com/blog2"/>
                </foaf:Person>
            </rdf:RDF>'''
        
        foaf_file = os.path.join(self.cache_dir, 'test_foaf.rdf')
        with open(foaf_file, 'w', encoding='utf-8') as f:
            f.write(foaf_data)

        # Parse the FOAF file
        feeds = foaf.parse_foaf(foaf_file)

        # Check that the feeds were parsed correctly
        self.assertEqual(len(feeds), 2)
        self.assertIn('http://example.com/blog1', feeds)
        self.assertIn('http://example.com/blog2', feeds)

    def test_parse_foaf_with_invalid_xml(self):
        """Test parsing an invalid FOAF file"""
        # Create an invalid FOAF file
        foaf_data = '''<?xml version="1.0" encoding="utf-8"?>
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                     xmlns:foaf="http://xmlns.com/foaf/0.1/">
                <foaf:Person>
                    <foaf:name>Test Person</foaf:name>
                    <foaf:weblog rdf:resource="http://example.com/blog"/>
                </foaf:Person>
            </rdf:RDF'''
        
        foaf_file = os.path.join(self.cache_dir, 'test_foaf.rdf')
        with open(foaf_file, 'w', encoding='utf-8') as f:
            f.write(foaf_data)

        # Parse the FOAF file
        feeds = foaf.parse_foaf(foaf_file)

        # Check that no feeds were parsed
        self.assertEqual(len(feeds), 0)

if __name__ == '__main__':
    unittest.main()
