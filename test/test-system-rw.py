# -*- coding: utf-8 -*-

from apitest import TestBase

"""
This module is used for testing new unit tests
When the test method is completted it is move som test-api.py

use 'nosetest -v -s unit-devel.py' to run the tests
"""


class TestAPIDevel(TestBase):

    def __init__(self, methodName='runTest'):
        TestBase.__init__(self, methodName)

    def test_InstallRemove(self):
        '''
        System: Install and Remove
        '''
        print()
        # Make sure that the test packages is not installed
        rc, output = self.Remove('foo bar')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        # Both test packages should be uninstalled now
        self.assertFalse(self._is_installed('foo'))
        self.assertFalse(self._is_installed('bar'))
        # Install the test packages
        print("Installing Test Packages : foo bar")
        rc, output = self.Install('foo bar')
        print('  Return Code : %i' % rc)
        self.assertEqual(rc, True)
        self.show_transaction_result(output)
        self.assertGreater(len(output), 0)
        for action, pkgs in output:
            self.assertEqual(action, u'install')
            self.assertGreater(len(pkgs), 0)
        self.RunTransaction()
        # Both test packages should be installed now
        self.assertTrue(self._is_installed('foo'))
        self.assertTrue(self._is_installed('bar'))
        # Remove the test packages
        print("Removing Test Packages : foo bar")
        rc, output = self.Remove('foo bar')
        print('  Return Code : %i' % rc)
        self.assertEqual(rc, True)
        self.show_transaction_result(output)
        self.assertGreater(len(output), 0)
        for action, pkgs in output:
            self.assertEqual(action, u'remove')
            self.assertGreater(len(pkgs), 0)
        self.RunTransaction()

    def test_Reinstall(self):
        '''
        System: Reinstall
        '''
        # install test package
        rc, output = self.Install('foo')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        self.assertTrue(self._is_installed('foo'))
        rc, output = self.Reinstall('foo')
        print('  Return Code : %i' % rc)
        self.assertTrue(rc)
        self.show_transaction_result(output)
        self.assertGreater(len(output), 0)
        for action, pkgs in output:
            self.assertEqual(action, u'reinstall')
            self.assertEqual(len(pkgs), 1)
        self.RunTransaction()
        self.assertTrue(self._is_installed('foo'))
        # cleanup again
        rc, output = self.Remove('foo')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        self.assertFalse(self._is_installed('foo'))

    def test_DowngradeUpdate(self):
        '''
        System: DownGrade & Update
        '''
        print()
        rc, output = self.Install('foo')
        if rc:
            self.show_transaction_result(output)
            self.RunTransaction()
        rc, output = self.Downgrade('foo')
        print('  Return Code : %i' % rc)
        print('  output : %s' % output)
        self.assertTrue(rc)
        self.show_transaction_result(output)
        self.assertGreater(len(output), 0)
        for action, pkgs in output:
            self.assertEqual(action, u'downgrade')
            self.assertGreater(len(pkgs), 0)
        self.RunTransaction()
        rc, output = self.Update('foo')
        print('  Return Code : %i' % rc)
        self.assertTrue(rc)
        self.show_transaction_result(output)
        self.assertGreater(len(output), 0)
        for action, pkgs in output:
            self.assertEqual(action, u'update')
            self.assertGreater(len(pkgs), 0)
        self.RunTransaction()

    def test_Transaction(self):
        '''
        System: AddTransaction, GetTransaction, ClearTransaction
        '''
        print()
        self._remove_if_installed('foo')  # make sure pkg is not installed
        rc, trans = self._add_to_transaction('foo')
        self.assertTrue(rc)
        self.show_transaction_result(trans)
        for action, pkglist in trans:
            self.assertEqual(action, 'install')
            self.assertIsInstance(pkglist, list)  # is a list
            self.assertEqual(len(pkglist), 1)
        # Clear the current goal/transaction
        self.ClearTransaction()
        rc, trans = self.GetTransaction()
        print("clear", trans)
        self.assertIsInstance(trans, list)  # is a list
        self.assertEqual(len(trans), 0)  # this should be an empty list
        # install 0xFFFF
        rc, trans = self._add_to_transaction('foo')
        self.assertTrue(rc)
        self.show_transaction_result(trans)
        for action, pkglist in trans:
            self.assertEqual(action, 'install')
            self.assertIsInstance(pkglist, list)  # is a list
            self.assertEqual(len(pkglist), 1)
        self.BuildTransaction()
        self.RunTransaction()
        # remove 0xFFFF
        rc, trans = self._add_to_transaction('foo')
        self.assertTrue(rc)
        self.show_transaction_result(trans)
        for action, pkglist in trans:
            self.assertEqual(action, 'remove')
            self.assertIsInstance(pkglist, list)  # is a list
            self.assertEqual(len(pkglist), 1)
        self.BuildTransaction()
        self.RunTransaction()

    def test_SetConfig(self):
        '''
        System: SetConfig
        '''
        print()
        before = self.GetConfig("fastestmirror")
        print("fastestmirror=%s" % before)
        rc = self.SetConfig("fastestmirror", True)
        self.assertTrue(rc)
        after = self.GetConfig("fastestmirror")
        self.assertTrue(after)
        rc = self.SetConfig("fastestmirror", False)
        self.assertTrue(rc)
        after = self.GetConfig("fastestmirror")
        self.assertFalse(after)
        rc = self.SetConfig("fastestmirror", before)
        self.assertTrue(rc)
        after = self.GetConfig("fastestmirror")
        self.assertEqual(after, before)
        rc = self.SetConfig("fastestmirror", True)
        self.assertTrue(rc)
        # check setting unknown conf setting
        rc = self.SetConfig("thisisnotfound", True)
        self.assertFalse(rc)

    def test_TransactionDepRemove(self):
        '''
        System: AddTransaction (Remove with deps)
        '''
        print()
        self._enable_default_repos()
        if not self._is_installed('btanks'):
            rc, output = self.Install('btanks')
            if rc:
                self.show_transaction_result(output)
                self.RunTransaction()
        rc, trans = self._add_to_transaction('btanks')
        self.show_transaction_result(trans)
        for action, pkglist in trans:
            self.assertEqual(action, 'remove')
            self.assertIsInstance(pkglist, list)  # is a list
            self.assertEqual(len(pkglist), 2)
        rc, trans = self.BuildTransaction()
        self.RunTransaction()

    def test_GroupInstall(self):
        """ System: GroupInstall & GroupRemove
        """
        print()
        self._enable_default_repos()
        # make sure firefox group is not installed
        print('install firefox group (1)')
        rc, output = self.GroupInstall("firefox")
        print(rc, output)
        if not rc:  # firefox group is installed (remove & install)
            print('remove firefox group (1)')
            rc, output = self.GroupRemove("firefox")
            print(rc, output)
            self.assertTrue(rc)
            self.RunTransaction()
            print('install firefox group (2)')
            rc, output = self.GroupInstall("firefox")
            self.assertTrue(rc)
            self.RunTransaction()
        else:  # firefox is not installed (install & remove)
            self.RunTransaction()
            print('remove firefox group (2)')
            rc, output = self.GroupRemove("firefox")
            print(rc, output)
            self.assertTrue(rc)
            self.RunTransaction()
