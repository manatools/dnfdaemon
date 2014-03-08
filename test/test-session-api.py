import sys, os
sys.path.insert(0,os.path.abspath('client'))
#from base import TestBaseReadonly as TestBase
from base import TestBase, TestBaseReadonly
from dnfdaemon import LockedError
from subprocess import check_output, call
from nose.exc import SkipTest
import time

"""
This module is used for testing new unit tests
When the test method is completted it is move som test-api.py

use 'nosetest -v -s unit-devel.py' to run the tests
"""

class TestAPIDevel(TestBaseReadonly):

    def __init__(self, methodName='runTest'):
        TestBaseReadonly.__init__(self, methodName)

    def test_Locking(self):
        '''
        Session: Unlock and Lock
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

    def test_GetPackages(self):
        '''
        Session: GetPackages
        '''
        print
        for narrow in ['installed','available']:
            print(' Getting packages : %s' % narrow)
            pkgs = self.GetPackages(narrow)
            self.assertIsInstance(pkgs, list)
            self.assertGreater(len(pkgs),0) # the should be more than once
            print('  packages found : %s ' % len(pkgs))
            pkg_id = pkgs[-1] # last pkg in list
            print(pkg_id)
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

    def test_GetPackagesByName(self):
        '''
        Session: GetPackagesByName
        '''
        print
        print "Get all available versions of yum"
        pkgs = self.GetPackagesByName('yum', newest_only=False)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        num1 = len(pkgs)
        self.assertNotEqual(num1, 0) # yum should always be there
        for pkg in pkgs:
            print "  Package : %s" % pkg
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            self.assertEqual(n,"yum")
        print "Get newest versions of yum"
        pkgs = self.GetPackagesByName('yum', newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        num2 = len(pkgs)
        self.assertEqual(num2, 1) # there can only be one :)
        for pkg in pkgs:
            print "  Package : %s" % pkg
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            self.assertEqual(n,"yum")
        print "Get the newest packages starting with yum-plugin-"
        pkgs = self.GetPackagesByName('yum-plugin-*', newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        num3 = len(pkgs)
        self.assertGreater(num3, 1) # there should be more than one :)
        for pkg in pkgs:
            print "  Package : %s" % pkg
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            self.assertTrue(n.startswith('yum'))

    def test_Repositories(self):
        '''
        Session: GetRepository and GetRepo
        '''
        print
        print("  Getting enabled repos")
        repos = self.GetRepositories('')
        self.assertIsInstance(repos, list)
        for repo_id in repos:
            print("    Repo : %s" % repo_id)
        print "  Getting *-source repos"
        repos = self.GetRepositories('*-source')
        self.assertIsInstance(repos, list)
        for repo_id in repos:
            print("    Repo : %s" % repo_id)
            self.assertTrue(repo_id.endswith('-source'))
        print("  \nGetting fedora repository")
        repo = self.GetRepo('updates')
        self.assertIsInstance(repo, dict)
        print("  Repo: fedora")
        print("  Name : %s " % repo['name'])
        print("  Metalink :\n  %s " % repo['metalink'])
        print("  enabled : %s " % repo['enabled'])
        print("  gpgcheck : %s " % repo['gpgcheck'])

        # check for a repo not there
        repo = self.GetRepo('XYZCYZ')
        self.assertIsNone(repo)


    def test_Search(self):
        '''
        Session: Search
        '''
        fields = ['name','summary']
        keys = ['yum','plugin']
        pkgs = self.Search(fields, keys ,True,True,False)
        self.assertIsInstance(pkgs, list)
        for p in pkgs:
            summary = self.GetAttribute(p,'summary')
            print str(p),summary
            self.assertTrue(keys[0] in str(p) or keys[0] in summary)
            self.assertTrue(keys[1] in str(p) or keys[1] in summary)
        keys = ['yum','zzzzddddsss'] # second key should not be found
        pkgs = self.Search(fields, keys ,True,True, False)
        self.assertIsInstance(pkgs, list)
        print "found %i packages" % len(pkgs)
        self.assertEqual(len(pkgs), 0) # when should not find any matches
        keys = ['yum','zzzzddddsss'] # second key should not be found
        pkgs = self.Search(fields, keys ,False, True, False)
        self.assertIsInstance(pkgs, list)
        print "found %i packages" % len(pkgs)
        self.assertGreater(len(pkgs), 0) # we should find some matches
        # retro should match some pkgtags
        keys = ['retro'] # second key should not be found
        pkgs = self.Search(fields, keys ,True, True, True)
        self.assertIsInstance(pkgs, list)
        print "found %i packages" % len(pkgs)
        self.assertGreater(len(pkgs), 0) # we should find some matches

    def test_PackageActions(self):
        """
        Session: GetPackageWithAttributes & GetAttribute (action)
        """
        print()
        flt_dict = {'installed':['remove'],'updates':['update'],'obsoletes':['obsolete'], 'available':['install','remove','update','obsolete']}
        for flt in flt_dict.keys():
            now = time.time()
            result = self.GetPackageWithAttributes(flt, ['summary','size'])
            print("%s, # = %s, time = %.3f" % (flt, len(result),time.time()-now))
            self.assertIsInstance(result, list) # result is a list
            i = 0
            for elem in result:
                self.assertIsInstance(elem, list) # each elem is a list
                self.assertEqual(len(elem),3) # 3 elements
                i += 1
                if i > 10: break # only test the first 10 elements
                now = time.time()
                action = self.GetAttribute(elem[0], 'action')
                name =  elem[0].split(",")[0]
                print("    %s = %s , time = %.3f" % (name, action, time.time()-now))
                self.assertIn(action, flt_dict[flt])


    def test_Groups(self):
        """
        Session: Groups (GetGroups & GetGroupPackages)
        """

        result = self.GetGroups()
        for cat, grps in result:
            # cat: [category_id, category_name, category_desc]
            self.assertIsInstance(cat, list) # cat is a list
            self.assertIsInstance(grps, list) # grps is a list
            self.assertEqual(len(cat),3) # cat has 3 elements
            print " --> %s" % cat[0]
            for grp in grps:
                # [group_id, group_name, group_desc, group_is_installed]
                self.assertIsInstance(grp, list) # grp is a list
                self.assertEqual(len(grp),4) # grp has 4 elements
                print "   tag: %s name: %s \n       desc: %s \n       installed : %s " % tuple(grp)
                # Test GetGroupPackages
                grp_id = grp[0]
                pkgs = self.GetGroupPackages(grp_id,'all')
                self.assertIsInstance(pkgs, list) # cat is a list
                print "       # of Packages in group         : ",len(pkgs)
                pkgs = self.GetGroupPackages(grp_id,'default')
                self.assertIsInstance(pkgs, list) # cat is a list
                print "       # of Default Packages in group : ",len(pkgs)

    def test_Downgrades(self):
        '''
        Session: GetAttribute( downgrades )
        '''
        print "Get newest versions of yum"
        pkgs = self.GetPackagesByName('yum', newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        num2 = len(pkgs)
        self.assertEqual(num2, 1) # there can only be one :)
        downgrades = self.GetAttribute(pkgs[0], 'downgrades')
        self.assertIsInstance(downgrades, list)
        (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkgs[0])
        inst_evr = "%s:%s.%s" % (e,v,r)
        print("Installed : %s" % pkgs[0])
        for id in downgrades:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(id)
            evr = "%s:%s.%s" % (e,v,r)
            self.assertTrue(evr < inst_evr)
            print("  Downgrade : %s" % id)

    def test_GetConfig(self):
        '''
        Session: GetConfig
        '''
        all_conf = self.GetConfig('*')
        self.assertIsInstance(all_conf, dict)
        for key in all_conf:
            print "   %s = %s" % (key,all_conf[key])
        fastestmirror = self.GetConfig('fastestmirror')
        print("fastestmirror : %s" % fastestmirror)
        self.assertIn(fastestmirror, [True,False])
        not_found = self.GetConfig('not_found')
        print("not_found : %s" % not_found)
        self.assertIsNone(not_found)





