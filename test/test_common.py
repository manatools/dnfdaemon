# -*- coding: utf-8 -*-

import dnfdaemon.server
import dnfdaemon.server.backend as backend

import test.support as support
import json
import logging
from unittest import mock

TEST_LOCAL_PKG = 'local-pkg,0,1.0,1.fc22,noarch,@commandline'


class DnfBaseMock(backend.DnfBase):

    def __init__(self, parent, repo='main'):
        self._base = support.MockBase(repo)
        self.parent = mock.MagicMock()
        self.md_progress = backend.MDProgress(parent)
        self.progress = backend.Progress(parent, max_err=100)
        self._packages = None

    def setup_base(self):
        self._packages = backend.Packages(self._base)

    def __getattr__(self, attr):
        if hasattr(self._base, attr):
            return getattr(self._base, attr)
        else:
            raise AttributeError

    def do_transaction(self, display):
        return True, ['no message']

    def download_packages(self, to_dnl, progress):
        pass

    def close(self):
        pass


class TestPackages(support.TestCase):

    def test_packages(self):
        """Test Packages()"""
        base = support.MockBase('main')
        pkgs = backend.Packages(base)
        inst = list(map(str, pkgs.installed))
        self.assertEqual(inst, ['bar-1.0-1.noarch',
                                'foo-2.0-1.noarch',
                                'bar-old-1.0-1.noarch',
                                'old-bar-1.0-1.noarch'])
        avail = list(map(str, pkgs.available))
        self.assertEqual(avail, ['bar-2.0-1.noarch',
                                 'foo-dep-err-1.0-1.noarch',
                                 'bar-dep-err-1.0-1.noarch',
                                 'bar-new-2.0-1.noarch',
                                 'petzoo-1.0-1.noarch'])
        upds = list(map(str, pkgs.updates))
        self.assertEqual(upds, ['bar-2.0-1.noarch'])
        obs = list(map(str, pkgs.obsoletes))
        self.assertEqual(obs, ['bar-new-2.0-1.noarch'])


class TestMultilpleUpdates(support.TestCase):

    def test_packages(self):
        """Test multiple updates for same pkg"""
        base = support.MockBase('updates')
        pkgs = backend.Packages(base)
        inst = list(map(str, pkgs.installed))
        self.assertEqual(inst, ['bar-1.0-1.noarch',
                                'foo-2.0-1.noarch',
                                'bar-old-1.0-1.noarch',
                                'old-bar-1.0-1.noarch'])
        avail = list(map(str, pkgs.get_all(showdups=True)))
        self.assertEqual(avail, ['bar-1.5-1.noarch',
                                 'bar-2.0-1.noarch'])
        upds = list(map(str, pkgs.updates))
        self.assertEqual(upds, ['bar-2.0-1.noarch'])


class TestDnfBase(support.TestCase):

    def setUp(self):
        self.base = DnfBaseMock(None)
        self.base.setup_base()

    def test_packages_attr(self):
        """Test packages attr"""
        self.assertIsInstance(self.base.packages, backend.Packages)

    def test_search_nodups(self):
        """Test search (nodups)"""
        found = self.base.search(['name'], ['foo'], showdups=False)
        res = list(map(str, found))
        self.assertEqual(res, ['foo-2.0-1.noarch',
                               'foo-dep-err-1.0-1.noarch'])

    def test_search_dups(self):
        """Test search (dups)"""
        found = self.base.search(['name'], ['foo'], showdups=True)
        res = list(map(str, found))
        #print(res)

        self.assertEqual(res, ['foo-2.0-1.noarch',
                               'foo-2.0-1.noarch',
                               'foo-dep-err-1.0-1.noarch',
                               'foo-1.0-1.noarch'])


class TestCommonBase(support.TestCase):

    def _get_base(self, reset=False, load_sack=True):
        if not self._base or reset:
            self._base = DnfBaseMock(self)
            if load_sack:
                self._base.setup_base()
        return self._base

    def setUp(self):
        self._base = None
        self.daemon = dnfdaemon.server.DnfDaemonBase()
        self.daemon._base = self._get_base()


class TestBrokenDeps(TestCommonBase):

    def _get_base(self, reset=False, load_sack=True):
        if not self._base or reset:
            self._base = DnfBaseMock(self, repo='broken')
            if load_sack:
                self._base.setup_base()
        return self._base

    def test_broken(self):
        print()
        res = json.loads(self.daemon.get_packages('available', []))
        self.assertEqual(res, ['broken,0,1.0,1,noarch,broken',
                              'dep01,0,1.0,1,noarch,broken'])
        rc, msgs = json.loads(self.daemon.install('broken'))
        #print(rc, msgs)
        self.assertEqual(False, rc)
        self.assertEqual(['nothing provides not-found-dep01 >= '
                          '1-0 needed by dep01-1.0-1.noarch'], msgs)

    def test_add_transaction_install_broken(self):
        # install pkg with broken deps
        pkg_id = 'broken,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [False, ['nothing provides not-found-dep01 >= 1-0 '
                     'needed by dep01-1.0-1.noarch']])


class TestCommonMisc(TestCommonBase):

    def test_base(self):
        """Test Packages class"""
        base = self.daemon.base
        self.assertIsNotNone(base)

    def test_get_repositories(self):
        repos = self.daemon.get_repositories('enabled')
        self.assertEqual(repos, ['main'])

    def test_get_config(self):
        # read all conf
        cfg = self.daemon.get_config('*')
        self.assertEqual(len(json.loads(cfg)), 37)
        # read single conf
        cfg = self.daemon.get_config('debuglevel')
        self.assertEqual(json.loads(cfg), 8)

    def test_get_packages(self):
        # only need to check on pkg_filter, to check the return format
        # other filters are checked in the TestPackages tests.
        pkgs = self.daemon.get_packages('installed', ['size'])
        self.assertEqual(json.loads(pkgs),
            [['bar,0,1.0,1,noarch,@System', 0],
             ['foo,0,2.0,1,noarch,@System', 0],
             ['bar-old,0,1.0,1,noarch,@System', 0],
             ['old-bar,0,1.0,1,noarch,@System', 0]])

        pkgs = self.daemon.get_packages('installed', [])
        self.assertEqual(json.loads(pkgs),
            ['bar,0,1.0,1,noarch,@System',
             'foo,0,2.0,1,noarch,@System',
             'bar-old,0,1.0,1,noarch,@System',
             'old-bar,0,1.0,1,noarch,@System'])

    def test_get_attribute(self):
        pkg_id = 'bar,0,2.0,1,noarch,main'
        attr = self.daemon.get_attribute(pkg_id, 'size')
        self.assertEqual(json.loads(attr), 0)

    def test_get_attribute_fake(self):
        pkg_id = 'bar,0,2.0,1,noarch,main'
        attr = self.daemon.get_attribute(pkg_id, 'action')
        self.assertEqual(json.loads(attr), 'update')
        # FIXME: updateinfo, changelog, filelist not supported
        # in dnf yet, so they just return None for now.FA
        attr = self.daemon.get_attribute(pkg_id, 'updateinfo')
        self.assertEqual(json.loads(attr), None)
        attr = self.daemon.get_attribute(pkg_id, 'changelog')
        self.assertEqual(json.loads(attr), None)
        attr = self.daemon.get_attribute(pkg_id, 'filelist')
        self.assertEqual(json.loads(attr), None)

    def test_search_with_attr_all(self):
        """Test search_with_attr (all)"""
        fields = ['name']
        keys = ['bar']
        attrs = []
        match_all = True
        newest_only = False
        tags = False
        found = self.daemon.search_with_attr(fields, keys, attrs,
                                              match_all, newest_only,
                                              tags)
        self.assertEqual(json.loads(found),
            ['bar,0,1.0,1,noarch,@System',
             'bar-old,0,1.0,1,noarch,@System',
             'old-bar,0,1.0,1,noarch,@System',
             'bar,0,1.0,1,noarch,main',
             'bar-old,0,1.0,1,noarch,main',
             'bar,0,2.0,1,noarch,main',
             'bar-dep-err,0,1.0,1,noarch,main',
             'bar-new,0,2.0,1,noarch,main'])

    def test_search_with_attr_new(self):
        """Test search_with_attr (newest)"""
        fields = ['name']
        keys = ['bar']
        attrs = []
        match_all = True
        newest_only = True
        tags = False
        found = self.daemon.search_with_attr(fields, keys, attrs,
                                              match_all, newest_only,
                                              tags)
        self.assertEqual(json.loads(found),
            ['bar-old,0,1.0,1,noarch,@System',
             'old-bar,0,1.0,1,noarch,@System',
             'bar,0,2.0,1,noarch,main',
             'bar-dep-err,0,1.0,1,noarch,main',
             'bar-new,0,2.0,1,noarch,main'])

    def test_get_packages_by_name_with_attr(self):
        """Test get_packages_by_name_with_attr"""
        attrs = []
        pkgs = self.daemon.get_packages_by_name_with_attr('foo', attrs, True)
        self.assertEqual(json.loads(pkgs), ["foo,0,2.0,1,noarch,@System"])
        pkgs = self.daemon.get_packages_by_name_with_attr('foo', attrs, False)
        self.assertEqual(json.loads(pkgs),
            ["foo,0,2.0,1,noarch,@System",
             "foo,0,1.0,1,noarch,main"])
        pkgs = self.daemon.get_packages_by_name_with_attr('*dep*',
                                                           attrs, True)
        self.assertEqual(json.loads(pkgs),
            ["foo-dep-err,0,1.0,1,noarch,main",
             "bar-dep-err,0,1.0,1,noarch,main"])


class TestCommonGroups(TestCommonBase):

    def setUp(self):
        TestCommonBase.setUp(self)
        #common.doTextLoggerSetup(logroot='dnf', loglvl=logging.DEBUG)
        #self.daemon.base.conf.debuglevel = 9
        self.daemon.base.read_mock_comps()

    def test_get_groups(self):
        res = self.daemon.get_groups()
        #print(json.loads(res))
        self.assertEqual(json.loads(res),
            [[["Base System", "Base System",
               "Various core pieces of the system."],
             [["inst-grp", "Inst Test Group", "--", True],
              ["test-grp", "Test Group", "--", False]]]]
            )

    def test_get_group_pkgs(self):
        """Test get_group_pkgs"""
        grp_id = 'test-grp'
        grp_flt = 'all'
        fields = []
        pkgs = self.daemon.get_group_pkgs(grp_id, grp_flt, fields)
        self.assertEqual(json.loads(pkgs),
            ['bar,0,2.0,1,noarch,main', 'petzoo,0,1.0,1,noarch,main'])
        grp_flt = ''
        pkgs = self.daemon.get_group_pkgs(grp_id, grp_flt, fields)
        self.assertEqual(json.loads(pkgs),
            ['petzoo,0,1.0,1,noarch,main'])

    def test_group_install(self):
        """Test group_install"""
        cmds = "test-grp"
        prst = self.daemon.base.group_persistor
        p_grp = prst.group(cmds)
        self.assertFalse(p_grp.installed)
        res = self.daemon.group_install(cmds)
        self.assertEqual(json.loads(res),
        [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        self.assertTrue(p_grp.installed)
        # try to install already installed group
        cmds = "inst-grp"
        res = self.daemon.group_install(cmds)
        self.assertEqual(json.loads(res),
            [False, "Group 'Inst Test Group' is already installed."])

    def test_group_remove(self):
        """Test group_remove"""
        cmds = "inst-grp"
        prst = self.daemon.base.group_persistor
        #print(json.dumps(prst.db.dct))
        p_grp = prst.group(cmds)
        self.assertTrue(p_grp.installed)
        res = self.daemon.group_remove(cmds)
        #print(json.loads(res))
        self.assertFalse(p_grp.installed)
        #print(json.dumps(prst.db.dct))


class TestCommonInstall(TestCommonBase):

    def test_install(self):
        cmds = 'petzoo'
        res = self.daemon.install(cmds)
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_install_local(self):
        # install local rpm
        res = self.daemon.install(support.LOCAL_RPM)
        self.assertEqual(json.loads(res),
            [True, [['install', [[TEST_LOCAL_PKG,
             6520.0, []]]]]])

    def test_remove(self):
        cmds = 'bar'
        res = self.daemon.remove(cmds)
        self.assertEqual(json.loads(res),
            [True, [['remove', [['bar,0,1.0,1,noarch,@System', 0.0, []]]]]])

    def test_update(self):
        cmds = 'bar'
        res = self.daemon.update(cmds)
        self.assertEqual(json.loads(res),
            [True, [['update', [['bar,0,2.0,1,noarch,main', 0.0, []]]]]])

    def test_update_obsolete(self):
        cmds = 'bar-new'
        res = self.daemon.update(cmds)
        expected = [True, [['install', [['bar-new,0,2.0,1,noarch,main',
                    0.0, ['bar-old,0,1.0,1,noarch,@System',
                          'old-bar,0,1.0,1,noarch,@System']]]]]]
        self.assertEqual(json.loads(res), expected)

    def test_install_obsolete(self):
        cmds = 'bar-new'
        res = self.daemon.install(cmds)
        expected = [True, [['install', [['bar-new,0,2.0,1,noarch,main',
                    0.0, ['bar-old,0,1.0,1,noarch,@System',
                          'old-bar,0,1.0,1,noarch,@System']]]]]]
        self.assertEqual(json.loads(res), expected)

    def test_downgrade(self):
        cmds = 'foo'
        res = self.daemon.downgrade(cmds)
        self.assertEqual(json.loads(res),
            [True, [['downgrade', [['foo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_reinstall(self):
        cmds = 'foo'
        res = self.daemon.reinstall(cmds)
        self.assertEqual(json.loads(res),
            [True, [['reinstall', [['foo,0,2.0,1,noarch,main', 0.0, []]]]]])


class TestCommonTransaction(TestCommonBase):

    def test_add_transaction_install(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # install no existing pkg_id
        pkg_id = 'not-found,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [False, ['Cant find package object for : '
                 'not-found,0,1.0,1,noarch,main']])

    def test_add_transaction_install_local(self):
        pkg_id = support.LOCAL_RPM
        res = self.daemon.add_transaction(pkg_id, 'localinstall')
        self.assertEqual(json.loads(res),
            [True, [['install', [[TEST_LOCAL_PKG,
             6520.0, []]]]]])

    def test_add_transaction_remove(self):
        pkg_id = 'bar,0,1.0,1,noarch,@System'
        res = self.daemon.add_transaction(pkg_id, 'remove')
        self.assertEqual(json.loads(res),
            [True, [['remove', [['bar,0,1.0,1,noarch,@System', 0.0, []]]]]])

    def test_add_transaction_update(self):
        pkg_id = 'bar,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'update')
        self.assertEqual(json.loads(res),
            [True, [['update', [['bar,0,2.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_downgrade(self):
        pkg_id = 'foo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'downgrade')
        self.assertEqual(json.loads(res),
            [True, [['downgrade', [['foo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_reinstall(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'reinstall')
        self.assertEqual(json.loads(res),
            [True, [['reinstall', [['foo,0,2.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_illegal(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'illegal')
        self.assertEqual(json.loads(res), [False, []])

    def test_add_transaction_already_installed(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [False, []])

    def test_transaction_misc(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # test _get_transaction()
        trans = self.daemon.get_transaction()
        self.assertEqual(json.loads(trans),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # test _clear_transaction()
        self.daemon.clear_transaction()
        trans = self.daemon.get_transaction()
        self.assertEqual(json.loads(trans), [False, []])

    def test_build_transaction(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # test _get_transaction()
        trans = self.daemon.build_transaction()
        #print(json.loads(trans))
        self.assertEqual(json.loads(trans),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_get_packages_to_download(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        pkgs = self.daemon._get_packages_to_download()
        self.assertEqual(str(pkgs[0]), 'petzoo-1.0-1.noarch')

    def test_run_transaction(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        res = self.daemon.run_transaction(max_err=10)
        self.assertEqual(json.loads(res), [0, []])
