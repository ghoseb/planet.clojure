#!/usr/bin/env python3

import os
import sys
import unittest
import logging
from xml.dom import minidom

import planet
from planet import config, themes

class ThemesTestCase(unittest.TestCase):
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

    def test_apply_theme(self):
        """Test applying a theme"""
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

        # Create a test theme
        theme_dir = os.path.join(self.output_dir, 'theme')
        if not os.path.exists(theme_dir):
            os.makedirs(theme_dir)

        # Create theme template
        template = '''<?xml version="1.0" encoding="utf-8"?>
            <html>
                <head><title>Test Theme</title></head>
                <body>
                    <h1>Test Theme</h1>
                    <div class="entries">
                        <?python
                        for entry in entries:
                            print(f'<div class="entry"><h2>{entry.title}</h2></div>')
                        ?>
                    </div>
                </body>
            </html>'''
        
        template_file = os.path.join(theme_dir, 'index.html.tmpl')
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(template)

        # Create theme CSS
        css = '''body { font-family: Arial, sans-serif; }
                .entry { margin: 1em 0; }'''
        
        css_file = os.path.join(theme_dir, 'style.css')
        with open(css_file, 'w', encoding='utf-8') as f:
            f.write(css)

        # Apply the theme
        themes.apply_theme(theme_dir)

        # Check that the theme was applied
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, 'index.html')))
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, 'style.css')))

    def test_apply_theme_with_custom_template(self):
        """Test applying a theme with a custom template"""
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

        # Create a test theme
        theme_dir = os.path.join(self.output_dir, 'theme')
        if not os.path.exists(theme_dir):
            os.makedirs(theme_dir)

        # Create custom template
        template = '''<?xml version="1.0" encoding="utf-8"?>
            <html>
                <head><title>Custom Theme</title></head>
                <body>
                    <h1>Custom Theme</h1>
                    <div class="entries">
                        <?python
                        for entry in entries:
                            print(f'<div class="entry"><h2>{entry.title}</h2><p>{entry.content}</p></div>')
                        ?>
                    </div>
                </body>
            </html>'''
        
        template_file = os.path.join(theme_dir, 'custom.html.tmpl')
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(template)

        # Apply the theme with custom template
        themes.apply_theme(theme_dir, template_file='custom.html.tmpl')

        # Check that the theme was applied
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, 'custom.html')))

if __name__ == '__main__':
    unittest.main()
