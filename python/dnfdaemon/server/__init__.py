# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

# (C) 2013 - 2014 - Tim Lauridsen <timlau@fedoraproject.org>

"""
Common stuff for the dnfdaemon dbus services
"""

from datetime import datetime
from dnf.exceptions import DownloadError
from dnf.yum.rpmtrans import TransactionDisplay
from gi.repository import GLib
from . import backend

import dbus
import dbus.service
import dbus.glib
import dnf
import dnf.const
import dnf.conf
import dnf.exceptions
import dnf.callback
import dnf.comps
import dnf.subject
import dnf.transaction
import dnf.yum
import json
import logging
import operator
import sys

VERSION = 105  # (00.01.02) must be integer
MAINLOOP = GLib.MainLoop()

# Fake attributes, there is simulating real package attribute
# used by get_attributes and others
FAKE_ATTR = ['downgrades', 'action', 'pkgtags',
             'changelog', 'filelist', 'updateinfo']

NONE = json.dumps(None)

_ACTIVE_DCT = {
    dnf.transaction.DOWNGRADE: operator.attrgetter('installed'),
    dnf.transaction.ERASE: operator.attrgetter('erased'),
    dnf.transaction.INSTALL: operator.attrgetter('installed'),
    dnf.transaction.REINSTALL: operator.attrgetter('installed'),
    dnf.transaction.UPGRADE: operator.attrgetter('installed'),
}


def _active_pkg(tsi):
    """Return the package from tsi that takes the active role
    in the transaction.
    """
    return _ACTIVE_DCT[tsi.op_type](tsi)

#------------------------------------------------------------ Callback handlers

logger = logging.getLogger('dnfdaemon.common')


def Logger(func):
    """
    This decorator catch yum exceptions and send fatal signal to frontend
    """
    def newFunc(*args, **kwargs):
        logger.debug("%s started args: %s " % (func.__name__, repr(args[1:])))
        rc = func(*args, **kwargs)
        logger.debug("%s ended" % func.__name__)
        return rc

    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc


# FIXME: TransactionDisplay is not public API
class RPMTransactionDisplay(TransactionDisplay):

    def __init__(self, base):
        self.actions = {self.PKG_CLEANUP: 'cleanup',
                        self.PKG_DOWNGRADE: 'downgrade',
                        self.PKG_ERASE: 'erase',
                        self.PKG_INSTALL: 'install',
                        self.PKG_OBSOLETE: 'obsolete',
                        self.PKG_REINSTALL: 'reinstall',
                        self.PKG_UPGRADE: 'update'}

        super(TransactionDisplay, self).__init__()
        self.base = base

    def event(self, package, action, te_current, te_total, ts_current,
              ts_total):
        """
        @param package: A yum package object or simple string of a package name
        @param action: A constant transaction set state
        @param te_current: current number of bytes processed in the transaction
                           element being processed
        @param te_total: total number of bytes in the transaction element being
                         processed
        @param ts_current: number of processes completed in whole transaction
        @param ts_total: total number of processes in the transaction.
        """
        if package:
            # package can be both str or dnf package object
            if not isinstance(package, str):
                pkg_id = self.base._get_id(package)
            else:
                pkg_id = package
            if action in self.actions:
                action = self.actions[action]
            self.base.RPMProgress(
                pkg_id, action, te_current, te_total, ts_current, ts_total)

    def scriptout(self, msgs):
        """msgs is the messages that were output (if any)."""
        pass


class DownloadCallback:
    """
    Dnf Download callback handler class
    """
    def __init__(self):
        pass

    def downloadStart(self, num_files, num_bytes):
        """ Starting a new parallel download batch """
        self.DownloadStart(num_files, num_bytes)  # send a signal

    def downloadProgress(self, name, frac, total_frac, total_files):
        """ Progress for a single instance in the batch """
        # send a signal
        self.DownloadProgress(name, frac, total_frac, total_files)

    def downloadEnd(self, name, status, msg):
        """ Download of af single instace ended """
        if not status:
            status = -1
        if not msg:
            msg = ""
        self.DownloadEnd(name, status, msg)  # send a signal

    def repoMetaDataProgress(self, name, frac):
        """ Repository Metadata Download progress """
        self.RepoMetaDataProgress(name, frac)


class DnfDaemonBase(dbus.service.Object, DownloadCallback):

    def __init__(self):
        self.logger = logging.getLogger('dnfdaemon.base')
        self.authorized_sender = set()
        self._lock = None
        self._base = None
        self._can_quit = True
        self._is_working = False
        self._watchdog_count = 0
        self._watchdog_disabled = False
        # time to daemon is closed when unlocked
        self._timeout_idle = 20
        # time to daemon is closed when locked and not working
        self._timeout_locked = 600
        self._obsoletes_list = None     # Cache for obsoletes

    @property
    def base(self):
        """
        yumbase property so we can auto initialize it if not defined
        """
        if not self._base:
            self._get_base()
        return self._base

#=========================================================================
# The action methods for the DBUS API (Session & System)
# RunTransaction -> run_transaction, etc
#=========================================================================

    def search_with_attr(self, fields, keys, attrs, match_all, newest_only,
                          tags):
        """Search for for packages, where given fields contain given key words

        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param attrs: list of extra attributes to get
        :param match_all: match all flag, if True return only packages
                          matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags
        """
        # FIXME: Add support for search in pkgtags, when supported in dnf
        showdups = not newest_only
        pkgs = self.base.search(fields, keys, match_all, showdups)
        values = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(values)

    def expire_cache(self):
        """Expire the dnf cache."""

        try:
            self.base.expire_cache()
            self.base.reset(sack=True)
            self.base.setup_base()
            return True
        except dnf.exceptions.RepoError as e:
            self.logger.error(str(e))
            self.ErrorMessage(str(e))
            return False

    def get_groups(self):
        """Get available comps categories & groups"""
        all_groups = []
        if not self.base.comps:  # lazy load the comps metadata
            self.base.read_comps()
        for category in self.base.comps.categories_iter():
            cat = (category.name, category.ui_name, category.ui_description)
            cat_grps = []
            for obj in category.group_ids:
                # get the dnf group obj
                grp = self.base.comps.group_by_pattern(obj.name)
                if grp:
                    # FIXME: no dnf API to get if group is installed
                    p_grp = self.base.group_persistor.group(grp.id)
                    if p_grp:
                        installed = p_grp.installed
                    else:
                        installed = False
                    elem = (grp.id, grp.ui_name,
                            grp.ui_description, installed)
                    cat_grps.append(elem)
            cat_grps.sort()
            all_groups.append((cat, cat_grps))
        all_groups.sort()
        return json.dumps(all_groups)

    def get_repositories(self, filter):
        """Get repository ids, based on a filter

        :param filter: filter to limit the listed repositories
        """
        if filter == '' or filter == 'enabled':
            repos = [repo.id for repo in self.base.repos.iter_enabled()]
        else:
            repos = [repo.id for repo in self.base.repos.get_matching(filter)]
        return repos

    def get_config(self, setting):
        """Get dnf config value(s)

        :param setting: name of setting (debuglevel etc..)

        if settings = '*', all keys/values is returned
        """
        if setting == '*':  # Return all config
            cfg = self.base.conf
            data = [(c, getattr(cfg, c)) for c in cfg.iterkeys()]
            all_conf = dict(data)
            value = json.dumps(all_conf)
        elif hasattr(self.base.conf, setting):
            value = json.dumps(getattr(self.base.conf, setting))
        else:
            value = json.dumps(None)
        return value

    def get_repo(self, repo_id):
        """Get information about a given repo_id

        :param repo_id: repo id to get information from
        """
        value = json.dumps(None)
        repo = self.base.repos.get(repo_id, None)  # get the repo object
        if repo:
            repo_conf = dict([(c, getattr(repo, c)) for c in repo.iterkeys()])
            value = json.dumps(repo_conf)
        return value

    def set_enabled_repos(self, repo_ids):
        """Enable a list of repos, disable the ones not in list"""
        self._reset_base()
        self._get_base(reset=True, load_sack=False)
        for repo in self.base.repos.all():
            if repo.id in repo_ids:
                logger.debug("  enabled : %s ", repo.id)
                repo.enable()
            else:
                repo.disable()
        self._base.setup_base()  # load the sack with the current enabled repos

    def get_packages(self, pkg_filter, attrs):
        """Get packages and attribute values based on a filter.

        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        :param attrs: list of attributes to get.
        """
        value = []
        if pkg_filter in ['installed', 'available', 'updates', 'obsoletes',
                          'recent', 'extras']:
            pkgs = getattr(self.base.packages, pkg_filter)
            value = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(value)

    def get_attribute(self, id, attr):
        """Get package attribute.

        :param id: yum package id
        :param attr: name of attribute (summary, size, description,
                     changelog etc..)
        """
        po = self._get_po(id)
        if po:
            if attr in FAKE_ATTR:  # is this a fake attr:
                value = json.dumps(self._get_fake_attributes(po, attr))
            elif hasattr(po, attr):
                value = json.dumps(getattr(po, attr))
            else:
                value = json.dumps(None)
        else:
            value = json.dumps(None)
        return value

    def get_packages_by_name_with_attr(self, name, attrs, newest_only):
        """get packages matching a name wildcard with given attributes."""
        pkgs = self._get_po_by_name(name, newest_only)
        values = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(values)

    def get_group_pkgs(self, grp_id, grp_flt, attrs):
        """Get packages & attributes for a given group id and
        group package type.
        """
        pkgs = []
        grp = self.base.comps.group_by_pattern(grp_id)
        if grp:
            if grp_flt == 'all':
                pkg_filters = [dnf.comps.MANDATORY,
                               dnf.comps.DEFAULT,
                               dnf.comps.OPTIONAL]
            else:
                pkg_filters = [dnf.comps.MANDATORY,
                               dnf.comps.DEFAULT]
            best_pkgs = []
            for pkg in grp.packages_iter():
                if pkg.option_type in pkg_filters:
                    best_pkgs.extend(self._get_po_by_name(pkg.name, True))
            pkgs = self.base.packages.filter_packages(best_pkgs)
        else:
            pass
        value = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(value)

    def group_install(self, cmds):
        """Install groups"""
        value = 0
        for cmd in cmds.split(' '):
            pkg_types = ["mandatory", "default"]
            grp = self._find_group(cmd)
            if grp:
                try:
                    self.base.group_install(grp, pkg_types)
                except dnf.exceptions.CompsError as e:
                    return json.dumps((False, str(e)))
        value = self.build_transaction()
        return value

    def group_remove(self, cmds):
        """Remove groups"""
        value = 0
        for cmd in cmds.split(' '):
            grp = self._find_group(cmd)
            if grp:
                try:
                    self.base.group_remove(grp)
                except dnf.exceptions.CompsError as e:
                    return json.dumps((False, str(e)))
        value = self.build_transaction()
        return value

    def install(self, cmds):
        """Install packages from pkg-specs."""
        value = 0
        for cmd in cmds.split(' '):
            if cmd.endswith('.rpm'):  # install local .rpm
                po = self.base.add_remote_rpm(cmd)
                self.base.package_install(po)
            else:
                try:
                    self.base.install(cmd)
                except dnf.exceptions.MarkingError:
                    pass
        value = self.build_transaction()
        return value

    def remove(self, cmds):
        """Remove packages from pkg-specs."""
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.remove(cmd)
        # ignore if the package is not installed
        except dnf.exceptions.PackagesNotInstalledError:
            pass
        value = self.build_transaction()
        return value

    def update(self, cmds):
        """Update packages from pkg-specs."""
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.upgrade(cmd)
        # ignore if the package is not installed
        except dnf.exceptions.PackagesNotInstalledError:
            pass
        value = self.build_transaction()
        return value

    def reinstall(self, cmds):
        """Reinstall packages from pkg-specs."""
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.reinstall(cmd)
        # ignore if the package is not installed
        except dnf.exceptions.PackagesNotInstalledError:
            pass
        value = self.build_transaction()
        return value

    def downgrade(self, cmds):
        """downgrade packages from pkg-specs."""
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.downgrade(cmd)
        # ignore if the package is not installed
        except dnf.exceptions.PackagesNotInstalledError:
            pass
        value = self.build_transaction()
        return value

    def add_transaction(self, pkg_id, action):
        """Add package id to transaction with a given action"""
        value = json.dumps((False, []))
        # localinstall has the path to the local rpm, not pkg_id
        if action != "localinstall":
            po = self._get_po(pkg_id)
            if not po:
                msg = "Cant find package object for : %s" % pkg_id
                self.ErrorMessage(msg)
                value = json.dumps((False, [msg]))
                return value
        rc = 0
        try:
            if action == 'install':
                rc = self.base.package_install(po)
            elif action == 'remove':
                rc = self.base.remove(str(po))
            elif action == 'update':
                rc = self.base.package_upgrade(po)
            elif action == 'obsolete':
                rc = self.base.package_upgrade(po)
            elif action == 'reinstall':
                rc = self.base.package_install(po)
            elif action == 'downgrade':
                rc = self.base.package_downgrade(po)
            elif action == 'localinstall':
                po = self.base.add_remote_rpm(pkg_id)
                rc = self.base.package_install(po)
            else:
                logger.error("unknown action : %s", action)
        # ignore if the package is not installed
        except dnf.exceptions.PackagesNotInstalledError:
            self.logger.warning("package not installed : ", str(po))
            self.ErrorMessage("package not installed : ", str(po))
        if rc:
            value = json.dumps(self._get_transaction_list())
            #value = json.dumps(self._get_goal_list())
        return value

    def clear_transaction(self):
        """Clear the current transaction."""
        self.base.reset(goal=True)  # reset the current goal

    def get_transaction(self):
        """Get the current transaction."""
        value = json.dumps(self._get_transaction_list())
        return value

    def build_transaction(self):
        """Resolve dependencies of current transaction."""
        self.TransactionEvent('start-build', NONE)
        value = json.dumps(self._get_transaction_list())
        self.TransactionEvent('end-build', NONE)
        return value

    def run_transaction(self, max_err):
        """Apply the current transaction to the system.

        It will download the needed packages and apply actions in the
        current transaction to the system
        """
        self.TransactionEvent('start-run', NONE)
        self.base.set_max_error(max_err)
        rc = 0
        msgs = []
        to_dnl = self._get_packages_to_download()
        try:
            if to_dnl:
                data = [self._get_id(po) for po in to_dnl]
                self.TransactionEvent('pkg-to-download', data)
                self.TransactionEvent('download', NONE)
                self.base.download_packages(to_dnl, self.base.progress)
            self.TransactionEvent('run-transaction', NONE)
            display = RPMTransactionDisplay(self)  # RPM Display callback
            self._can_quit = False
            rc, msgs = self.base.do_transaction(display=display)
        except DownloadError as e:
            rc = 4  # Download errors
            if isinstance(e.errmap, dict):
                msgs = e.errmap
                error_msgs = []
                for fn in msgs:
                    for msg in msgs[fn]:
                        error_msgs.append("%s : %s" % (fn, msg))
                        self.logger.debug("  %s : %s" % (fn, msg))
                msgs = error_msgs
            else:
                msgs = [str(e)]
                print("DEBUG:", msgs)
        self._can_quit = True
        self._reset_base()
        self.TransactionEvent('end-run', NONE)
        result = json.dumps((rc, msgs))
        # FIXME: It should not be needed to call .success_finish()
        return result

    def get_history_by_days(self, start, end):
        """Get the history transaction by a give date interval.

        :param start: start days from today
        :param end: end days from today
        """
        # FIXME: Base.history is not public api
        # https://bugzilla.redhat.com/show_bug.cgi?id=1079526
        result = []
        now = datetime.now()
        history = self.base.history.old(complete_transactions_only=False)
        i = 0
        result = []
        while i < len(history):
            ht = history[i]
            i += 1
            print("DBG: ", ht, ht.end_timestamp)
            if not ht.end_timestamp:
                continue
            tm = datetime.fromtimestamp(ht.end_timestamp)
            delta = now - tm
            if delta.days < start:  # before start days
                continue
            elif delta.days > end:  # after end days
                break
            result.append(ht)
        value = json.dumps(self._get_id_time_list(result))
        return value

    def history_search(self, pattern):
        """
        search in yum history
        :param pattern: list of search patterns
        :type pattern: list
        """
        # FIXME: Base.history is not public api
        # https://bugzilla.redhat.com/show_bug.cgi?id=1079526
        result = []
        tids = self.base.history.search(pattern)
        if len(tids) > 0:
            result = self.base.history.old(tids)
        else:
            result = []
        value = json.dumps(self._get_id_time_list(result))
        return value

    def get_history_transaction_pkgs(self, tid):
        """Get the package transactions for given transaction id."""
        # FIXME: Base.history is not public api
        # https://bugzilla.redhat.com/show_bug.cgi?id=1079526
        result = []
        tx = self.base.history.old([tid], complete_transactions_only=False)
        result = []
        for pkg in tx[0].trans_data:
            values = [pkg.name, pkg.epoch, pkg.version,
                      pkg.release, pkg.arch, pkg.ui_from_repo]
            pkg_id = ",".join(values)
            elem = (pkg_id, pkg.state, pkg.state_installed)
            result.append(elem)
        value = json.dumps(result)
        return value

    def set_option(self, option, value):
        """Set an DNF config option to a given value."""
        value = json.loads(value)
        if hasattr(self.base.conf, option):
            setattr(self.base.conf, option, value)
            self.logger.debug("Setting Option %s = %s" % (option, value))
            for repo in self.base.repos.iter_enabled():
                if hasattr(repo, option):
                    setattr(repo, option, value)
                    self.logger.debug(
                        "Setting Option %s = %s (%s)", option, value, repo.id)
            return True
        else:
            return False
        pass

    def handle_gpg_import(self, gpg_info):
        """Callback for handling af user confirmation of gpg key import.

        :param gpg_info: dict with info about gpg key
        {"po": ..,  "userid": .., "hexkeyid": .., "keyurl": ..,
          "fingerprint": .., "timestamp": ..)
        """
        print(gpg_info)
        pkg_id = self._get_id(gpg_info['po'])
        userid = gpg_info['userid']
        hexkeyid = gpg_info['hexkeyid']
        keyurl = gpg_info['keyurl']
        #fingerprint = gpg_info['fingerprint']
        timestamp = gpg_info['timestamp']
        # the gpg key has not been confirmed by the user
        if not hexkeyid in self._gpg_confirm:
            self._gpg_confirm[hexkeyid] = False
            self.GPGImport(pkg_id, userid, hexkeyid, keyurl, timestamp)
        return self._gpg_confirm[hexkeyid]

#=========================================================================
# Helper methods
#=========================================================================

    def _get_po_by_name(self, name, newest_only):
        """Get packages matching a name pattern.

        :param name: name pattern
        :param newest_only: True = get newest packages only
        """
        subj = dnf.subject.Subject(name)
        qa = subj.get_best_query(self.base.sack, with_provides=False)
        if newest_only:
            qa = qa.latest()
        pkgs = self.base.packages.filter_packages(qa)
        return pkgs

    def _find_group(self, pattern):
        """ Find comps.Group object by pattern."""
        if not self.base.comps:  # lazy load the comps metadata
            self.base.read_comps()
        grp = self.base.comps.group_by_pattern(pattern)
        return grp

    def _get_packages_to_download(self):
        """Get packages to download for the current dnf transaction."""
        to_dnl = []
        for tsi in self.base.transaction:
            if tsi.installed:
                to_dnl.append(tsi.installed)
        return to_dnl

    def _get_transaction_list(self):
        """Get a list of the current transaction."""
        out_list = []
        sublist = []
        rc, tx_list = self._make_trans_dict()
        if rc:
            for (action, pkglist) in [('install', tx_list['install']),
                ('update', tx_list['update']),
                ('remove', tx_list['remove']),
                ('reinstall', tx_list['reinstall']),
                    ('downgrade', tx_list['downgrade'])]:

                for tsi in pkglist:
                    po = _active_pkg(tsi)
                    (n, a, e, v, r) = po.pkgtup
                    size = float(po.size)
                    # build a list of obsoleted packages
                    alist = []
                    for obs_po in tsi.obsoleted:
                        alist.append(self._get_id(obs_po))
                    if alist:
                        logger.debug(repr(alist))
                    el = (self._get_id(po), size, alist)
                    sublist.append(el)
                if pkglist:
                    out_list.append([action, sublist])
                    sublist = []
            return rc, out_list
        else:  # Error in depsolve, return error msgs
            return rc, tx_list

    def _make_trans_dict(self):
        """Get a dict of action & packages from the current transaction"""
        b = {}
        for t in ('downgrade', 'remove', 'install', 'reinstall', 'update'):
            b[t] = []
        # Resolve to get the Transaction object popolated
        try:
            rc = self.base.resolve(allow_erasing=True)
            output = []
        except dnf.exceptions.DepsolveError as e:
            rc = False
            output = e.value.split('. ')
        if rc:
            for tsi in self.base.transaction:
                if tsi.op_type == dnf.transaction.DOWNGRADE:
                    b['downgrade'].append(tsi)
                elif tsi.op_type == dnf.transaction.ERASE:
                    b['remove'].append(tsi)
                elif tsi.op_type == dnf.transaction.INSTALL:
                    b['install'].append(tsi)
                elif tsi.op_type == dnf.transaction.REINSTALL:
                    b['reinstall'].append(tsi)
                elif tsi.op_type == dnf.transaction.UPGRADE:
                    b['update'].append(tsi)
            return rc, b
        else:
            return rc, output

    def _get_obsoletes(self):
        """Cache a list of obsoletes."""
        if not self._obsoletes_list:
            self._obsoletes_list = list(self.base.packages.obsoletes)
        return self._obsoletes_list

    def _get_update_info(self, po):
        """Get update info for a package."""
        # TODO : updateinfo is not supported in DNF yet
        # https://bugzilla.redhat.com/show_bug.cgi?id=850912
        if po:
            value = None
        else:
            value = None
        return value

    def _get_filelist(self, po):
        """Get filelist for a package."""
        # TODO : filelist is not supported in DNF yet
        if po:
            value = None
        else:
            value = None
        return value

    def _get_changelog(self, po):
        """Get changelog for a package."""
        # TODO : changelog is not supported in DNF yet
        # https://bugzilla.redhat.com/show_bug.cgi?id=1066867
        if po:
            value = None
        else:
            value = None
        return value

    def _get_po_list(self, po, attrs):
        """Get a list packages with given attributes."""
        if not attrs:
            return self._get_id(po)
        po_list = [self._get_id(po)]
        for attr in attrs:
            if attr in FAKE_ATTR:  # is this a fake attr:
                value = self._get_fake_attributes(po, attr)
            elif hasattr(po, attr):
                value = getattr(po, attr)
            else:
                value = None
            po_list.append(value)
        return po_list

    def _get_id_time_list(self, hist_trans):
        """Get a list of (tid, isodate) pairs from a list of
        history transactions.
        """
        result = []
        for ht in hist_trans:
            tm = datetime.fromtimestamp(ht.end_timestamp)
            result.append((ht.tid, tm.isoformat()))
        return result

    def _get_fake_attributes(self, po, attr):
        """Get pseudo attributes for a given package.

        :param attr: Fake attribute
        :type attr: string
        """
        if attr == "action":
            return self._get_action(po)
        elif attr == 'downgrades':
            return self._get_downgrades(po)
        elif attr == 'pkgtags':
            return self._get_pkgtags(po)
        elif attr == 'changelog':
            return self._get_changelog(po)
        elif attr == 'updateinfo':
            return self._get_update_info(po)
        elif attr == 'filelist':
            return self._get_filelist(po)

    def _get_downgrades(self, pkg):
        """Get available downgrades for a given <name.arch>."""
        pkg_ids = []
        q = self.base.sack.query()
        avail = q.available().filter(name=pkg.name, arch=pkg.arch).run()
        for apkg in avail:
            if pkg.evr_gt(apkg):
                pkg_ids.append(self._get_id(apkg))
        return pkg_ids

    def _get_pkgtags(self, po):
        """Get tags from a given package."""
        # TODO : pkgtags is not supported in DNF yet
        return []

    def _to_package_id_list(self, pkgs):
        """Get a sorted list of package ids from a list of packages.

        If and package is installed, the installed po id will be returned
        :param pkgs:
        """
        result = set()
        for po in sorted(pkgs):
            result.add(self._get_id(po))
        return result

    def _get_po(self, id):
        """Get the package from given package id."""
        n, e, v, r, a, repo_id = id.split(',')
        q = self.base.sack.query()
        if repo_id.startswith('@'):  # installed package
            f = q.installed()
            f = f.filter(name=n, version=v, release=r, arch=a)
            if len(f) > 0:
                return f[0]
            else:
                return None
        else:
            f = q.available()
            f = f.filter(name=n, version=v, release=r, arch=a)
            if len(f) > 0:
                return f[0]
            else:
                return None

    def _get_id(self, pkg):
        """Get a package id from a given package."""
        values = [
            pkg.name, str(pkg.epoch), pkg.version, pkg.release,
            pkg.arch, pkg.ui_from_repo]
        return ",".join(values)

    def _get_action(self, po):
        """Get the action for a given package.

        The action is what can be performed on the package
        an installed package will return as 'remove' as action
        an available update will return 'update'
        an available package will return 'install'

        :param po: package
        :return: action (remove, install, update, downgrade, obsolete)
        """
        action = 'install'
        n, a, e, v, r = po.pkgtup
        q = self.base.sack.query()
        if po.reponame.startswith('@'):
            action = 'remove'
        else:
            upd = q.upgrades().filter(name=n, version=v, release=r, arch=a)
            if upd:
                action = 'update'
            else:
                obsoletes = self._get_obsoletes()
                if po in obsoletes:
                    action = 'obsolete'
                else:
                    # get installed packages with same name
                    ipkgs = q.installed().filter(name=po.name).run()
                    if ipkgs:
                        ipkg = ipkgs[0]
                        if po.evr_gt(ipkg):
                            action = 'downgrade'
        return action

    def _get_base(self, reset=False, load_sack=True):
        """Get a cached dnf.Base object."""
        if not self._base or reset:
            self._base = backend.DnfBase(self)
            if load_sack:
                self._base.setup_base()
        return self._base

    def _reset_base(self):
        """Close the current dnf.Base object."""
        if self._base:
            self._base.close()
            self._base = None

    def _setup_watchdog(self):
        """Setup the DBUS service watchdog to run every second when idle."""
        GLib.timeout_add(1000, self._watchdog)

    def _watchdog(self):
        """Handle the DBUS service watchdog calls."""
        terminate = False
        if self._watchdog_disabled or self._is_working:  # is working
            return True
        if not self._lock:  # is locked
            if self._watchdog_count > self._timeout_idle:
                terminate = True
        else:
            if self._watchdog_count > self._timeout_locked:
                terminate = True
        if terminate:  # shall we quit
            if self._can_quit:
                self._reset_base()
                self.mainloop_quit()
        else:
            self._watchdog_count += 1
            self.logger.debug("Watchdog : %i" % self._watchdog_count)
            return True

    def mainloop_quit(self):
        MAINLOOP.quit()

    def mainloop_run(self):
        MAINLOOP.run()

    def TransactionEvent(self, event, data):
        """Transaction event stub, overload in child class

        Needed for unit testing
        """
        #print("event: %s" % event)
        pass

    def ErrorMessage(self, msg):
        """ErrorMessage stub, overload in child class

        Needed for unit testing
        """
        #print("error: %s" % msg)
        pass


def doTextLoggerSetup(logroot='dnfdaemon', logfmt='%(asctime)s: %(message)s',
                      loglvl=logging.INFO):
    """Setup Python logging."""
    logger = logging.getLogger(logroot)
    logger.setLevel(loglvl)
    formatter = logging.Formatter(logfmt, "%H:%M:%S")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.propagate = False
    logger.addHandler(handler)
