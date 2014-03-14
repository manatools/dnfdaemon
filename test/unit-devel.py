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
        super(TestAPIDevel, self).__init__(methodName)

    def test_AnyObsoletes(self):
        '''
        System: GetPackages(obsoletes)
        '''
        print()
        # make sure there is one update
        self._remove_if_installed('bar-new') # make sure pkg is not installed
        self._remove_if_installed('bar-old') # make sure pkg is not installed
        rc, output = self.Install('bar-old')
        self.assertTrue(rc)
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        for narrow in ['obsoletes']:
            print('  ==================== Getting packages : %s =============================' % narrow)
            pkgs = self.GetPackages(narrow)
            self.assertIsInstance(pkgs, list)
            print('  packages found : %s ' % len(pkgs))
            self.assertGreater(len(pkgs),0)
            for pkg in pkgs:
                print("    pkg: ", str(pkg))
        rc, output = self.Update('bar-new')
        self.assertTrue(rc)
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        self.assertTrue(self._is_installed('bar-new'))
        self.assertFalse(self._is_installed('bar-old'))
        self._remove_if_installed('bar-old') # make sure pkg is not installed


