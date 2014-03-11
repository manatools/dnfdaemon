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
        #TestBase.__init__(self, methodName)
        TestBaseReadonly.__init__(self, methodName)

    def test_GetPackages(self):
        '''
        Session: GetPackages
        '''
        print
        for narrow in ['installed','available']:
            print(' ******** Getting packages : %s ***************' % narrow)
            pkgs = self.GetPackages(narrow)
            self.assertIsInstance(pkgs, list)
            self.assertGreater(len(pkgs),1) # the should be more than once
            print('  packages found : %s ' % len(pkgs))
            if narrow == 'available':
                for pkg_id in pkgs:
                    self._show_package(pkg_id)
            else:
                pkg_id = pkgs[-1] # last pkg in list
                self._show_package(pkg_id)
        for narrow in ['updates','obsoletes','recent','extras']:
            print('  ==================== Getting packages : %s =============================' % narrow)
            pkgs = self.GetPackages(narrow)
            self.assertIsInstance(pkgs, list)
            print('  packages found : %s ' % len(pkgs))
            if len(pkgs) > 0:
                pkg_id = pkgs[0] # last pkg in list
                print(pkg_id)
                self._show_package(pkg_id)
        for narrow in ['notfound']: # Dont exist, but it should not blow up
            print(' Getting packages : %s' % narrow)
            pkgs = self.GetPackages(narrow)
            self.assertIsInstance(pkgs, list)
            self.assertEqual(len(pkgs),0) # the should be notting
            print('  packages found : %s ' % len(pkgs))



