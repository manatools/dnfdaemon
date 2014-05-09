import unittest
import datetime
import time
from datetime import date
from dnfdaemon.client import Client, ClientReadOnly


class TestBase(unittest.TestCase, Client):
    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)
        Client.__init__(self)
        self._gpg_confirm = None
        self._signals = {}
        self.default_repos = []

    def setUp(self):
        self.Lock()
        self.default_repos = self.GetRepositories('enabled')
        self._enable_test_repos()

    def tearDown(self):
        self.Unlock()
        time.sleep(2)

    def reset_signals(self):
        self._signals = {}

    def check_signal(self, name):
        if name in self._signals:
            return True
        else:
            return False

    def add_signal(self, name, parms="()"):
        ts = time.time()
        st = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        entry = (st, parms)
        if name in self._signals:
            self._signals[name].append(entry)
        else:
            self._signals[name] = [entry]

    def show_signals(self):
        for sig in self._signals:
            print("Signal : %s" % sig)
            for ts, parms in self._signals[sig]:
                print("  --> %s : %s" % (ts, parms))

    def show_changelog(self, changelog, max_elem=3):
        i = 0
        for (c_date, c_ver, msg) in changelog:
            i += 1
            if i > max_elem:
                return
            print("* %s %s" % (date.fromtimestamp(c_date).isoformat(), c_ver))
            for line in msg.split('\n'):
                print("%s" % line)

    def show_package_list(self, pkgs):
        for pkg_id in pkgs:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg_id)
            print(" --> %s-%s:%s-%s.%s (%s)" % (n, e, v, r, a, repo_id))

    def show_transaction_list(self, pkgs):
        for pkg_id in pkgs:
            pkg_id = str(pkg_id)
            (n, e, v, r, a, repo_id, ts_state) = self.to_txmbr_tuple(pkg_id)
            print(
                " --> %s-%s:%s-%s.%s (%s) - %s" %
                (n, e, v, r, a, repo_id, ts_state))

    def show_transaction_result(self, output):
        for action, pkgs in output:
            print("  %s" % action)
            for pkg in pkgs:
                print("  --> %s" % str(pkg))

# ======================== Helpers =======================

    def _enable_default_repos(self):
        self.SetEnabledRepos(self.default_repos)

    def _enable_test_repos(self):
        self.SetEnabledRepos(["dnf-daemon-test"])

    def _add_to_transaction(self, name):
        '''
        Helper to add a package to transaction
        '''
        pkgs = self.GetPackagesByName(name, newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        self.assertEqual(len(pkgs), 1)
        pkg = pkgs[0]
        (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
        if repo_id[0] == '@':
            action = 'remove'
        else:
            action = 'install'
        rc, trans = self.AddTransaction(pkg, action)
        return (rc, trans)

    def _remove_if_installed(self, name):
        rc, output = self.Remove(name)
        if rc:
            self.RunTransaction()

    def check_installed(self, name):
        pkgs = self.GetPackagesByName(name, newest_only=True)
        # pkgs should be a list instance
        for pkg in pkgs:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            if repo_id[0] == '@':
                return True
        return False

    def _is_installed(self, name):
        pkgs = self.GetPackagesByName(name, newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        self.assertTrue(len(pkgs) > 0)
        for pkg in pkgs:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            if repo_id[0] == '@':
                return True
        return False

    def _show_package(self, id):
        (n, e, v, r, a, repo_id) = self.to_pkg_tuple(id)
        print("\nPackage attributes")
        print("Name : %s " % n)
        summary = self.GetAttribute(id, 'summary')
        print("Summary : %s" % summary)
        print("\nDescription:")
        desc = self.GetAttribute(id, 'description')
        print(desc)
#         print( "\nChangelog:")
#         changelog = self.GetAttribute(id, 'changelog')
#         self.assertIsInstance(changelog, list)
#         self.show_changelog(changelog, max_elem=2)
        # Check a not existing attribute dont make it blow up

#
# Dbus Signal Handlers
#

    def on_TransactionEvent(self, event, data):
        values = (event, data)
        self.add_signal("TransactionEvent", repr(values))

    def on_RPMProgress(
            self, package, action, te_current, te_total, ts_current, ts_total):
        values = (package, action, te_current, te_total, ts_current, ts_total)
        self.add_signal("RPMProgress", repr(values))

    def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        self._signals.append("GPGImport")
        values = (pkg_id, userid, hexkeyid, keyurl, timestamp)
        self._gpg_confirm = values
        print("received signal : GPGImport%s" % (repr(values)))

    def on_DownloadStart(self, num_files, num_bytes):
        ''' Starting a new parallel download batch '''
        values = (num_files, num_bytes)
        self.add_signal("DownloadStart", repr(values))
        #print("on_DownloadStart : %s" % (repr(values)))

    def on_DownloadProgress(self, name, frac, total_frac, total_files):
        ''' Progress for a single instance in the batch '''
        values = (name, frac, total_frac, total_files)
        self.add_signal("DownloadProgress", repr(values))
        #print("on_DownloadProgress : %s" % (repr(values)))

    def on_DownloadEnd(self, name, status, msg):
        ''' Download of af single instace ended '''
        values = (name, status, msg)
        self.add_signal("DownloadEnd", repr(values))
        #print("on_DownloadEnd : %s" % (repr(values)))

    def on_RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        values = (name, frac)
        self.add_signal("RepoMetaDataProgress", repr(values))
        #print("on_RepoMetaDataProgress : %s" % (repr(values)))


class TestBaseReadonly(unittest.TestCase, ClientReadOnly):
    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)
        ClientReadOnly.__init__(self)
        self.default_repos = []
        self._signals = {}

    def setUp(self):
        self.Lock()
        self.default_repos = self.GetRepositories('enabled')
        self._enable_test_repos()

    def tearDown(self):
        self.Unlock()

    def reset_signals(self):
        self._signals = {}

    def check_signal(self, name):
        if name in self._signals:
            return True
        else:
            return False

    def add_signal(self, name, parms="()"):
        ts = time.time()
        st = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        entry = (st, parms)
        if name in self._signals:
            self._signals[name].append(entry)
        else:
            self._signals[name] = [entry]

    def show_signals(self):
        for sig in self._signals:
            print("Signal : %s" % sig)
            for ts, parms in self._signals[sig]:
                print("  --> %s : %s" % (ts, parms))

    def show_changelog(self, changelog, max_elem=3):
        i = 0
        for (c_date, c_ver, msg) in changelog:
            i += 1
            if i > max_elem:
                return
            print("* %s %s" % (date.fromtimestamp(c_date).isoformat(), c_ver))
            for line in msg.split('\n'):
                print("%s" % line)

    def show_package_list(self, pkgs):
        for pkg_id in pkgs:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg_id)
            print(" --> %s-%s:%s-%s.%s (%s)" % (n, e, v, r, a, repo_id))

    def _is_installed(self, name):
        pkgs = self.GetPackagesByName(name, newest_only=True)
        # pkgs should be a list instance
        self.assertIsInstance(pkgs, list)
        self.assertTrue(len(pkgs) > 0)
        for pkg in pkgs:
            (n, e, v, r, a, repo_id) = self.to_pkg_tuple(pkg)
            if repo_id[0] == '@':
                return True
        return False

    def _show_package(self, id):
        (n, e, v, r, a, repo_id) = self.to_pkg_tuple(id)
        print("\n   Package attributes")
        print("      Name : %s " % n)
        summary = self.GetAttribute(id, 'summary')
        print("      Summary : %s" % summary)
        print("\nDescription:")
        desc = self.GetAttribute(id, 'description')
        print(desc)

    def on_RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        values = (name, frac)
        self.add_signal("RepoMetaDataProgress", repr(values))
        #print("on_RepoMetaDataProgress : %s" % (repr(values)))

    def _enable_default_repos(self):
        self.SetEnabledRepos(self.default_repos)

    def _enable_test_repos(self):
        self.SetEnabledRepos(["dnf-daemon-test"])
