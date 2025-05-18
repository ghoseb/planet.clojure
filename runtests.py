#!/usr/bin/env python3

import os
import sys
import unittest
import logging

def run_tests():
    """Run all tests in the tests directory"""
    logging.basicConfig(level=logging.INFO)
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover('tests')
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_runner.run(test_suite)

if __name__ == '__main__':
    run_tests()
