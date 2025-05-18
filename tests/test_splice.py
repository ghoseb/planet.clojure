#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, splice

class SpliceTestCase(unittest.TestCase):
    def setUp(self):
        self.config = os.path.join(os.path.dirname(__file__), 'data', 'test.ini')
        config.load(self.config)
        self.cache_dir = config.cache_directory()
        self.output_dir = config.output_dir()
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def tearDown(self):
        if os.path.exists(self.cache_dir):
            for file in os.listdir(self.cache_dir):
                os.remove(os.path.join(self.cache_dir, file))
            os.rmdir(self.cache_dir)
        if os.path.exists(self.output_dir):
            for file in os.listdir(self.output_dir):
                os.remove(os.path.join(self.output_dir, file))
            os.rmdir(self.output_dir)

    def test_splice_planet(self):
        """Test splicing all feeds"""
        # Create test feeds
        for i in range(3):
            feed = minidom.parseString(f'''<?xml version="1.0" encoding="utf-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                    <title>Test Feed {i}</title>
                    <entry>
                        <title>Test Entry {i}</title>
                        <id>test-entry-{i}</id>
                        <published>2024-01-0{i+1}T00:00:00Z</published>
                    </entry>
                </feed>''')
            
            feed_file = os.path.join(self.cache_dir, f'test_feed_{i}.xml')
            with open(feed_file, 'w', encoding='utf-8') as f:
                f.write(feed.toxml())

        # Create test template
        template = '''<?xml version="1.0" encoding="utf-8"?>
            <html>
                <head><title>Test Planet</title></head>
                <body>
                    <h1>Test Planet</h1>
                    <div class="entries">
                        <?python
                        for entry in entries:
                            print(f'<div class="entry"><h2>{entry.title}</h2></div>')
                        ?>
                    </div>
                </body>
            </html>'''
        
        template_file = os.path.join(self.output_dir, 'index.html.tmpl')
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(template)

        # Splice the planet
        splice.splicePlanet()

        # Check that the output was generated
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, 'index.html')))

if __name__ == '__main__':
    unittest.main()
