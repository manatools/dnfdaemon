# -*- coding: utf-8 -*-

import dnfdaemon.server
import dnfdaemon.server.backend as backend

import datetime
import dnf.callback
import test.support as support
import hawkey
import json
import time
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


class TestProgress(support.TestCase):

    result = """DownloadStart(1, 10240)
DownloadProgress('foobar0-1.0-1.noarch', 0.1, 0.1, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.2, 0.2, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.3, 0.3, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.4, 0.4, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.5, 0.5, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.6, 0.6, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.7, 0.7, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.8, 0.8, 0)
DownloadProgress('foobar0-1.0-1.noarch', 0.9, 0.9, 0)
DownloadProgress('foobar0-1.0-1.noarch', 1.0, 1.0, 0)
DownloadEnd('foobar0-1.0-1.noarch', None, 'done')"""

    def _get_pload(self, num):
        return support.Payload('foobar{}-1.0-1.noarch'.format(num), 10 * 1024)

    def _simulate_download(self, progress, fnum):
        pload = self._get_pload(fnum)
        done = 0
        for fnum in range(0, 10):
            progress.progress(pload, done)
            done += 1024
        progress.progress(pload, 10 * 1024)
        progress.end(pload, dnf.callback.STATUS_OK, "done")

    def test_progress_single_file(self):
        """Test progress for downloading one file."""
        daemon = support.DaemonStub()
        progress = backend.Progress(daemon, 10)
        num_files = 1
        num_bytes = 1024 * 10 * num_files
        progress.start(num_files, num_bytes)
        for fnum in range(0, num_files):
            self._simulate_download(progress, fnum)
        self.assertEqual('\n'.join(daemon.get_calls()), TestProgress.result)

    def test_progress_multiple_files(self):
        """Test progress for downloading multiple files."""
        daemon = support.DaemonStub()
        progress = backend.Progress(daemon, 10)
        num_files = 10
        num_bytes = 1024 * 10 * num_files
        progress.start(num_files, num_bytes)
        for fnum in range(0, num_files):
            self._simulate_download(progress, fnum)
        calls = daemon.get_calls()
        self.assertEqual(len(calls), (num_files * 11) + 1)
        self.assertEqual(calls[0], "DownloadStart(%s, %s)" % (num_files, num_bytes))
        self.assertEqual(calls[-1],
                         "DownloadEnd('foobar%d-1.0-1.noarch', None, 'done')"
                         % (num_files - 1))

    def test_progress_mirrors(self):
        """Test progress for skipping mirrors."""
        daemon = support.DaemonStub()
        progress = backend.Progress(daemon, 10)
        pload = self._get_pload(0)
        done = 0
        progress.start(1, 1024 * 10)
        progress.progress(pload, done)
        # simulate mirror skip
        for fnum in range(0, 5):
            progress.end(pload, dnf.callback.STATUS_MIRROR, "new mirror")
        for fnum in range(0, 10):
            progress.progress(pload, done)
            done += 1024
        progress.progress(pload, 10 * 1024)
        progress.end(pload, dnf.callback.STATUS_OK, "done")
        # mirror skip is not errors
        self.assertEqual(progress._err_count, 0)
        self.assertEqual(progress.download_files, 1)
        calls = daemon.get_calls()
        # print("\n".join(calls))
        # check for mirror skip signals
        for ndx in range(1, 6):
            self.assertEqual(calls[ndx],
                             "DownloadEnd('foobar0-1.0-1.noarch', 3, 'new mirror')")

    def test_progress_max_err(self):
        """Test progress for failed downloads"""
        #print()
        daemon = support.DaemonStub()
        progress = backend.Progress(daemon, 10)
        num_files = 10
        num_bytes = 1024 * 10 * num_files
        max_err = int(num_files / 2)
        progress.start(num_files, num_bytes)
        self.assertEqual(progress.max_err, max_err)
        try:
            for fnum in range(0, num_files):
                pload = self._get_pload(fnum)
                progress.end(pload, dnf.callback.STATUS_FAILED,
                             "error in dnl : %d" % fnum)
        except dnf.exceptions.DownloadError:
            pass
        self.assertEqual(progress._err_count, max_err + 1)
        #calls = daemon.get_calls()
        #print("\n".join(calls))


class TestPackages(support.TestCase):

    def test_packages(self):
        """Test the backend packages"""
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


class TestAdvisory(support.TestCase):

    def test_advisory(self):
        """Test package advisories. """
        po = support.MockPackage('bar-2.0-1.noarch')
        updinfo = backend.UpdateInfo(po)
        adv_list = updinfo.advisories_list()
        print("\n", adv_list)
        self.assertEqual(len(adv_list), 2)
        adv = adv_list[0]
        # check main fields
        self.assertEqual(adv['id'], 'FEDORA-2015-1234')
        self.assertEqual(adv['description'],
                         'Advisory Description\nfoobar feature was added')
        self.assertEqual(adv['type'], hawkey.ADVISORY_BUGFIX)
        self.assertEqual(adv['title'], 'Advisory Title')
        self.assertEqual(adv['filenames'], ['bar-2.0-1.noarch.rpm'])
        self.assertEqual(adv['updated'], "2015-12-02 11:12:13")

        # check references
        ref = adv['references'][0]
        self.assertEqual(ref, [hawkey.REFERENCE_BUGZILLA,
                               '1234567',
                               'The foobar bug has been fixed',
                               'https://bugzilla.redhat.com'
                               '/show_bug.cgi?id=1234567'])


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
        """Test install of packages with broken deps"""
        res = json.loads(self.daemon.get_packages('available', []))
        self.assertEqual(res, ['broken,0,1.0,1,noarch,broken',
                              'dep01,0,1.0,1,noarch,broken'])
        rc, msgs = json.loads(self.daemon.install('broken'))
        self.assertEqual(False, rc)
        self.assertEqual(['nothing provides not-found-dep01 >= '
                          '1-0 needed by dep01-1.0-1.noarch'], msgs)

    def test_add_transaction_install_broken(self):
        """Test add_transaction  of packages with broken deps"""
        pkg_id = 'broken,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
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
        self.assertEqual(json.loads(attr), [])
        attr = self.daemon.get_attribute(pkg_id, 'changelog')
        self.assertEqual(json.loads(attr), None)
        attr = self.daemon.get_attribute(pkg_id, 'filelist')
        self.assertEqual(json.loads(attr), [])
        attr = self.daemon.get_attribute(pkg_id, 'requires')
        self.assertEqual(json.loads(attr), {})

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

    def test_get_actions(self):
        """Test package actions"""
        attrs = ['action']
        pkgs = self.daemon.get_packages_by_name_with_attr('foo',
                                                           attrs, False)
        self.assertEqual(json.loads(pkgs),
            [['foo,0,2.0,1,noarch,@System', 'remove'],
             ['foo,0,1.0,1,noarch,main', 'downgrade']
            ])



class TestCommonGroups(TestCommonBase):

    def setUp(self):
        TestCommonBase.setUp(self)
        #common.doTextLoggerSetup(logroot='dnf', loglvl=logging.DEBUG)
        #self.daemon.base.conf.debuglevel = 9
        self.daemon.base.read_mock_comps()

    def test_get_groups(self):
        res = self.daemon.get_groups()
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
        p_grp = prst.group(cmds)
        self.assertTrue(p_grp.installed)
        self.daemon.group_remove(cmds)
        self.assertFalse(p_grp.installed)


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
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
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
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['install', [[TEST_LOCAL_PKG,
             6520.0, []]]]]])

    def test_add_transaction_remove(self):
        pkg_id = 'bar,0,1.0,1,noarch,@System'
        res = self.daemon.add_transaction(pkg_id, 'remove')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['remove', [['bar,0,1.0,1,noarch,@System', 0.0, []]]]]])

    def test_add_transaction_update(self):
        pkg_id = 'bar,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'update')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['update', [['bar,0,2.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_downgrade(self):
        pkg_id = 'foo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'downgrade')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['downgrade', [['foo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_reinstall(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'reinstall')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['reinstall', [['foo,0,2.0,1,noarch,main', 0.0, []]]]]])

    def test_add_transaction_illegal(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'illegal')
        self.assertEqual(json.loads(res), [False, []])

    def test_add_transaction_already_installed(self):
        pkg_id = 'foo,0,2.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res), [False, []])

    def test_transaction_misc(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # test _get_transaction()
        trans = self.daemon.get_transaction()
        self.assertEqual(json.loads(trans),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        # test _clear_transaction()
        self.daemon.clear_transaction()
        trans = self.daemon.build_transaction()
        self.assertEqual(json.loads(trans), [False, []])

    def test_build_transaction(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        trans = self.daemon.build_transaction()
        self.assertEqual(json.loads(trans),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])

    def test_get_packages_to_download(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        pkgs = self.daemon._get_packages_to_download()
        self.assertEqual(str(pkgs[0]), 'petzoo-1.0-1.noarch')

    def test_run_transaction(self):
        pkg_id = 'petzoo,0,1.0,1,noarch,main'
        res = self.daemon.add_transaction(pkg_id, 'install')
        self.assertEqual(json.loads(res), [True, []])
        res = self.daemon.build_transaction()
        self.assertEqual(json.loads(res),
            [True, [['install', [['petzoo,0,1.0,1,noarch,main', 0.0, []]]]]])
        res = self.daemon.run_transaction(max_err=10)
        self.assertEqual(json.loads(res), [0, []])
