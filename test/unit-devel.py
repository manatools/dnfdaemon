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

#class TestAPIDevel(TestBaseReadonly):
class TestAPIDevel(TestBase):

    def __init__(self, methodName='runTest'):
        TestBase.__init__(self, methodName)
        #TestBaseReadonly.__init__(self, methodName)


    def test_Transaction(self):
        '''
        System: AddTransaction (Remove with deps)
        '''
        print()
        self._enable_default_repos()
        rc, output = self.Install('btanks')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        rc, trans = self._add_to_transaction('btanks')
        self.show_transaction_result(trans)
        for action,pkglist in trans:
            self.assertEqual(action,'remove')
            self.assertIsInstance(pkglist, list) # is a list
            self.assertEqual(len(pkglist),2)
        rc,trans  = self.BuildTransaction()
        self.RunTransaction()
