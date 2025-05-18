#!/usr/bin/env python3

# portalocker.py - Cross-platform (posix/nt) API for flock-style file locking.
#                  Requires python 1.5.2 or better.
# See http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/65203/index_txt
# Except where otherwise noted, recipes in the Python Cookbook are 
# published under the Python license.

"""Cross-platform (posix/nt) API for flock-style file locking.

Synopsis:

   import portalocker
   file = open("somefile", "r+")
   portalocker.lock(file, portalocker.LOCK_EX)
   file.seek(12)
   file.write("foo")
   file.close()

If you know what you're doing, you may choose to

   portalocker.unlock(file)

before closing the file, but why?

Methods:

   lock( file, flags )
   unlock( file )

Constants:

   LOCK_EX
   LOCK_SH
   LOCK_NB

I learned the win32 technique for locking files from sample code
provided by John Nielsen <nielsenjf@my-deja.com> in the documentation
that accompanies the win32 modules.

Author: Jonathan Feinberg <jdf@pobox.com>
Version: $Id: portalocker.py,v 1.3 2001/05/29 18:47:55 Administrator Exp $
"""

import os
import sys
import logging
import fcntl
import struct
import time

class LockError(Exception):
    """Exception raised when a lock cannot be acquired."""
    pass

def lock(file, flags):
    """Lock a file using fcntl."""
    try:
        fcntl.flock(file.fileno(), flags)
    except IOError as e:
        raise LockError(f"Failed to lock file: {e}")

def unlock(file):
    """Unlock a file."""
    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    except IOError as e:
        logging.error(f"Failed to unlock file: {e}")

class LockFile:
    def __init__(self, filename, mode='r', timeout=None):
        self.filename = filename
        self.mode = mode
        self.timeout = timeout
        self.file = None
        self.locked = False
        
    def __enter__(self):
        self.acquire()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        
    def acquire(self):
        """Acquire the lock."""
        if self.locked:
            return
            
        start_time = time.time()
        while True:
            try:
                self.file = open(self.filename, self.mode)
                lock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                return
            except LockError:
                if self.timeout is not None and time.time() - start_time > self.timeout:
                    raise LockError(f"Timeout waiting for lock on {self.filename}")
                time.sleep(0.1)
                
    def release(self):
        """Release the lock."""
        if not self.locked:
            return
            
        try:
            unlock(self.file)
            self.file.close()
        finally:
            self.locked = False
            self.file = None

if __name__ == '__main__':
	from time import time, strftime, localtime
	import sys
	import portalocker

	log = open('log.txt', "a+")
	portalocker.lock(log, portalocker.LOCK_EX)

	timestamp = strftime("%m/%d/%Y %H:%M:%S\n", localtime(time()))
	log.write( timestamp )

	print "Wrote lines. Hit enter to release lock."
	dummy = sys.stdin.readline()

	log.close()

