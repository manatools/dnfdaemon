# Copyright (C) 2012-2014  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

from __future__ import absolute_import
from __future__ import unicode_literals

import datetime
import dnf
import dnf.cli.cli
import dnf.cli.demand
import dnf.comps
import dnf.exceptions
import dnf.goal
import dnf.package
import dnf.persistor
import dnf.pycomp
import dnf.repo
import dnf.sack
import hawkey
import hawkey.test
import itertools
import os
import unittest

from unittest import mock

skip = unittest.skip

# testing infrastructure


def repo(reponame):
    return os.path.join(repo_dir(), reponame)


def repo_dir():
    this_dir = os.path.dirname(__file__)
    return os.path.join(this_dir, 'test_data/repos')

COMPS_PATH = os.path.join(repo_dir(), 'main_comps.xml')
LOCAL_RPM = os.path.join(repo_dir(), 'local-pkg-1.0-1.fc22.noarch.rpm')
# mock objects


def mock_comps(seed_persistor):
    comps = dnf.comps.Comps()
    comps.add_from_xml_filename(COMPS_PATH)

    persistor = MockGroupPersistor()
    if seed_persistor:
        p_som = persistor.group('inst-grp')
        p_som.pkg_types = dnf.comps.MANDATORY
        p_som.full_list.extend(('foo', 'bar'))

    return comps, persistor


class _BaseStubMixin(object):
    """A reusable class for creating `dnf.Base` stubs.

    See also: hawkey/test/python/__init__.py.

    Note that currently the used TestSack has always architecture set to
    "x86_64". This is to get the same behavior when running unit tests on
    different arches.

    """
    def __init__(self, *extra_repos):
        super(_BaseStubMixin, self).__init__()
        for r in extra_repos:
            repo = MockRepo(r, None)
            repo.enable()
            self._repos.add(repo)

        self._conf = FakeConf()
        self._persistor = FakePersistor()
        self._yumdb = MockYumDB()
        self.ds_callback = mock.Mock()

    @property
    def sack(self):
        if self._sack:
            return self._sack
        return self.init_sack()

    def _activate_group_persistor(self):
        return MockGroupPersistor()

    def activate_persistor(self):
        pass

    def init_sack(self):
        self._sack = TestSack(repo_dir(), self)
        self._sack.load_system_repo()
        for repo in self.repos.iter_enabled():
            fn = "%s.repo" % repo.id
            self._sack.load_test_repo(repo.id, fn)

        self._sack.configure(self.conf.installonlypkgs)
        self._goal = dnf.goal.Goal(self._sack)
        return self._sack

    def close(self):
        pass

    def read_mock_comps(self, seed_persistor=True):
        self._comps, self.group_persistor = mock_comps(seed_persistor)
        return self._comps

    def read_all_repos(self):
        pass


class HistoryStub(dnf.yum.history.YumHistory):
    """Stub of dnf.yum.history.YumHistory for easier testing."""

    def __init__(self):
        """Initialize a stub instance."""
        self.old_data_pkgs = {}

    def _old_data_pkgs(self, tid, sort=True):
        """Get packages of a transaction."""
        if sort:
            raise NotImplementedError('sorting not implemented yet')
        return self.old_data_pkgs.get(tid, ())[:]

    def close(self):
        """Close the history."""
        pass

    def old(self, tids=[], limit=None, *_args, **_kwargs):
        """Get transactions with given IDs."""
        create = lambda tid: dnf.yum.history.YumHistoryTransaction(self,
            (int(tid), 0, '0:685cc4ac4ce31b9190df1604a96a3c62a3100c35',
             1, '1:685cc4ac4ce31b9190df1604a96a3c62a3100c36', 0, 0))

        sorted_all_tids = sorted(self.old_data_pkgs.keys(), reverse=True)

        trxs = (create(tid) for tid in tids or sorted_all_tids
                if tid in self.old_data_pkgs)
        limited = trxs if limit is None else itertools.islice(trxs, limit)
        return tuple(limited)


class FakeAdvisoryRef(object):
    def __init__(self, ref_id, ref_type=hawkey.REFERENCE_BUGZILLA):
        self.id = ref_id
        self.type = ref_type
        self.title = 'The foobar bug has been fixed'
        self.url = 'https://bugzilla.redhat.com/show_bug.cgi?id=' + self.id


class FakeAdvisory(object):
    def __init__(self, pkg):
        self.id = 'FEDORA-2015-1234'
        self.description = "Advisory Description\nfoobar feature was added"
        self.type = hawkey.ADVISORY_BUGFIX
        self.title = 'Advisory Title'
        self.filenames = ['%s.rpm' % pkg]
        self.references = [FakeAdvisoryRef('1234567')]
        self.updated = datetime.datetime(2015, 12, 2, 11, 12, 13)

class MockPackage(object):
    def __init__(self, nevra, repo=None):
        self.baseurl = None
        self.chksum = (None, None)
        self.downloadsize = None
        self.header = None
        self.location = '%s.rpm' % nevra
        self.repo = repo
        self.reponame = None if repo is None else repo.id
        self.str = nevra
        (self.name, self.epoch, self.version, self.release, self.arch) = \
            hawkey.split_nevra(nevra)
        self.evr = '%(epoch)d:%(version)s-%(release)s' % vars(self)
        self.pkgtup = (self.name, self.arch, str(self.epoch), self.version,
                       self.release)

    def __str__(self):
        return self.str

    def localPkg(self):
        return os.path.join(self.repo.pkgdir, os.path.basename(self.location))

    def returnIdSum(self):
        return self.chksum

    def get_advisories(self, h_filter):
        return [FakeAdvisory(self.str)]

    @property
    def files(self):
        return ['/usr/bin/foobar', '/etc/foobar.conf']


class MockRepo(dnf.repo.Repo):
    def valid(self):
        return None

    def local(self):
        return True




class TestSack(hawkey.test.TestSackMixin, dnf.sack.Sack):
    def __init__(self, repo_dir, base):
        hawkey.test.TestSackMixin.__init__(self, repo_dir)
        dnf.sack.Sack.__init__(self,
                               arch=hawkey.test.FIXED_ARCH,
                               pkgcls=dnf.package.Package,
                               pkginitval=base,
                               make_cache_dir=True)


class MockBase(_BaseStubMixin, dnf.Base):
    """A class mocking `dnf.Base`."""


def mock_sack(*extra_repos):
    return MockBase(*extra_repos).sack


class MockYumDB(mock.Mock):
    def __init__(self):
        super(mock.Mock, self).__init__()
        self.db = {}

    def get_package(self, po):
        return self.db.setdefault(str(po), mock.Mock())

    def assertLength(self, length):
        assert(len(self.db) == length)


# mock object taken from testbase.py in yum/test:
class FakeConf(object):
    def __init__(self):
        self.assumeyes = None
        self.best = False
        self.cachedir = dnf.const.TMPDIR
        self.clean_requirements_on_remove = False
        self.color = 'never'
        self.color_update_installed = 'normal'
        self.color_update_remote = 'normal'
        self.color_list_available_downgrade = 'dim'
        self.color_list_available_install = 'normal'
        self.color_list_available_reinstall = 'bold'
        self.color_list_available_upgrade = 'bold'
        self.color_list_installed_extra = 'bold'
        self.color_list_installed_newer = 'bold'
        self.color_list_installed_older = 'bold'
        self.color_list_installed_reinstall = 'normal'
        self.color_update_local = 'bold'
        self.commands = []
        self.debug_solver = False
        self.debuglevel = 8
        self.defaultyes = False
        self.disable_excludes = []
        self.exclude = []
        self.groupremove_leaf_only = False
        self.history_record = False
        self.installonly_limit = 0
        self.installonlypkgs = ['kernel']
        self.installroot = '/'
        self.multilib_policy = 'best'
        self.obsoletes = True
        self.persistdir = '/should-not-exist-bad-test/persist'
        self.plugins = False
        self.protected_multilib = False
        self.protected_packages = []
        self.showdupesfromrepos = False
        self.tsflags = []
        self.verbose = False
        self.yumvar = {'releasever': 'Fedora69'}

    def iterkeys(self):
        """Yield the names of all defined options in the instance."""
        for name in self.__dict__:
            yield name


class FakePersistor(object):
    def get_expired_repos(self):
        return set()

    def reset_last_makecache(self):
        pass

    def since_last_makecache(self):
        return None


class MockGroupPersistor(dnf.persistor.GroupPersistor):
    """Empty persistor that doesn't need any I/O."""
    def __init__(self):
        self.db = self._empty_db()

# test cases


class TestCase(unittest.TestCase):
    def assertEmpty(self, collection):
        return self.assertEqual(len(collection), 0)

    def assertFile(self, path):
        """Assert the given path is a file."""
        return self.assertTrue(os.path.isfile(path))

    def assertLength(self, collection, length):
        return self.assertEqual(len(collection), length)

    def assertPathDoesNotExist(self, path):
        return self.assertFalse(os.access(path, os.F_OK))

    def assertStartsWith(self, string, what):
        return self.assertTrue(string.startswith(what))


class DaemonStub:

    def __init__(self):
        self._calls = []

    def add_call(self, msg):
        self._calls.append(msg)

    def get_calls(self):
        return self._calls

    def downloadStart(self, *args):
        """ Starting a new parallel download batch """
        msg = 'DownloadStart%s' % repr(args)
        self.add_call(msg)

    def downloadProgress(self, *args):
        """ Progress for a single instance in the batch """
        msg = 'DownloadProgress%s' % repr(args)
        self.add_call(msg)

    def downloadEnd(self, *args):
        """ Download of af single instace ended """
        msg = 'DownloadEnd%s' % repr(args)
        self.add_call(msg)


class Payload(object):

    def __init__(self, fn, size):
        self.fn = fn
        self.size = size

    def __str__(self):
        """Nice, human-readable representation. :api"""
        return self.fn

    @property
    def download_size(self):
        """Total size of the download. :api"""
        return self.size