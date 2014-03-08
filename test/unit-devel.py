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

    def test_Locking(self):
        '''
        System: Unlock and Lock
        '''
        print
        # release the lock (grabbed by setUp)
        self.Unlock()
        # calling a method without a lock should raise a YumLockedError
        # self.assertRaises(YumLockedError,self.Install, '0xFFFF')
        # trying to unlock method without a lock should raise a YumLockedError
        self.assertRaises(LockedError,self.Unlock)
        # get the Lock again, else tearDown will fail
        self.Lock()


    def test_InstallRemove(self):
        '''
        System: Install and Remove
        '''
        print()
        # Make sure that the test packages is not installed
        rc, output = self.Remove('0xFFFF Hermes')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        # Both test packages should be uninstalled now
        self.assertFalse(self._is_installed('0xFFFF'))
        self.assertFalse(self._is_installed('Hermes'))
        # Install the test packages
        print "Installing Test Packages : 0xFFFF Hermes"
        rc, output = self.Install('0xFFFF Hermes')
        print('  Return Code : %i' % rc)
        self.assertEqual(rc,True)
        self.show_transaction_result(output)
        self.assertGreater(len(output),0)
        for action, pkgs in output:
            self.assertEqual(action,u'install')
            self.assertGreater(len(pkgs),0)
        self.RunTransaction()
        # Both test packages should be installed now
        self.assertTrue(self._is_installed('0xFFFF'))
        self.assertTrue(self._is_installed('Hermes'))
        ## Remove the test packages
        #print "Removing Test Packages : 0xFFFF Hermes"
        #rc, output = self.Remove('0xFFFF Hermes')
        #print('  Return Code : %i' % rc)
        #self.assertEqual(rc,True)
        #self.show_transaction_result(output)
        #self.assertGreater(len(output),0)
        #for action, pkgs in output:
            #self.assertEqual(action,u'remove')
            #self.assertGreater(len(pkgs),0)
        #self.RunTransaction()
#