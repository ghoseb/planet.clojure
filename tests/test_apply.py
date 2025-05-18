#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom
from io import StringIO

import planet
from planet import config, splice

class ApplyTestCase(unittest.TestCase):
    def setUp(self):
        self.config = os.path.join(os.path.dirname(__file__), 'data', 'test.ini')
        config.load(self.config)

    def test_apply(self):
        """Test applying templates"""
        # Create a test document
        doc = minidom.parseString('<feed xmlns="http://www.w3.org/2005/Atom"/>')
        feed = doc.documentElement

        # Add some test entries
        for i in range(3):
            entry = doc.createElement('entry')
            title = doc.createElement('title')
            title.appendChild(doc.createTextNode(f'Test Entry {i}'))
            entry.appendChild(title)
            feed.appendChild(entry)

        # Apply templates
        splice.apply(doc)

        # Check output files
        output_dir = config.output_dir()
        self.assertTrue(os.path.exists(output_dir))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'index.html')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'atom.xml')))

    def test_apply_with_filters(self):
        """Test applying templates with filters"""
        # Create a test document
        doc = minidom.parseString('<feed xmlns="http://www.w3.org/2005/Atom"/>')
        feed = doc.documentElement

        # Add some test entries
        for i in range(3):
            entry = doc.createElement('entry')
            title = doc.createElement('title')
            title.appendChild(doc.createTextNode(f'Test Entry {i}'))
            entry.appendChild(title)
            feed.appendChild(entry)

        # Apply templates with filters
        config.parser.set('Planet', 'filters', 'regexp_sifter.py?require=Test')
        splice.apply(doc)

        # Check output files
        output_dir = config.output_dir()
        self.assertTrue(os.path.exists(output_dir))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'index.html')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'atom.xml')))

    def test_apply_with_bill_of_materials(self):
        """Test applying templates with bill of materials"""
        # Create a test document
        doc = minidom.parseString('<feed xmlns="http://www.w3.org/2005/Atom"/>')
        feed = doc.documentElement

        # Add some test entries
        for i in range(3):
            entry = doc.createElement('entry')
            title = doc.createElement('title')
            title.appendChild(doc.createTextNode(f'Test Entry {i}'))
            entry.appendChild(title)
            feed.appendChild(entry)

        # Apply templates with bill of materials
        config.parser.set('Planet', 'bill_of_materials', 'style.css')
        splice.apply(doc)

        # Check output files
        output_dir = config.output_dir()
        self.assertTrue(os.path.exists(output_dir))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'index.html')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'atom.xml')))
        self.assertTrue(os.path.exists(os.path.join(output_dir, 'style.css')))

if __name__ == '__main__':
    unittest.main()
