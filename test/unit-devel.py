from __future__ import print_function
from __future__ import absolute_import
import sys, os
sys.path.insert(0,os.path.abspath('client'))
#from base import TestBaseReadonly as TestBase
from base import TestBase, TestBaseReadonly
from dnfdaemon import LockedError
from subprocess import check_output, call
from nose.exc import SkipTest

"""
This module is used for testing new unit tests
When the test method is completted it is move som test-api.py

use 'nosetest -v -s unit-devel.py' to run the tests
"""

class TestAPIDevel(TestBaseReadonly):
#class TestAPIDevel(TestBase):

    def __init__(self, methodName='runTest'):
        super(TestAPIDevel, self).__init__(methodName)




