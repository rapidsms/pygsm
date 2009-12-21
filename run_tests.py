#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4

import os
import sys
import re
import unittest

DIR_PATH = os.curdir
EXTRA_PATHS = [
  DIR_PATH,
  os.path.join(DIR_PATH, 'lib'),
  os.path.join(DIR_PATH, 'test', 'messages'),
  os.path.join(DIR_PATH, 'test')
]

TEST_FILE_PATTERN = re.compile('([a-z]+_)+test\.py$')

def callback( arg, dirname, fnames ):
    for file in fnames:
		fullpath = os.path.join(dirname,file)
		if os.path.isfile(fullpath) and TEST_FILE_PATTERN.match(file, 1):
			files.append(file.replace('.py', ''))

if __name__ == '__main__':
  sys.path = EXTRA_PATHS + sys.path
  print sys.path
  files = []
  os.path.walk(os.path.join(DIR_PATH, 'test'),callback,files)
  loader = unittest.TestLoader()
  suite = unittest.TestSuite()
  for f in files:
	print f
	suite.addTests(loader.loadTestsFromName(f))
  unittest.TextTestRunner(verbosity=2).run(suite)
  		
