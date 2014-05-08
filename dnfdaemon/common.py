# -*- coding: utf-8 -*-
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
from __future__ import print_function
from __future__ import absolute_import

from datetime import datetime
from dnf.exceptions import DownloadError
from dnf.yum.rpmtrans import TransactionDisplay
from time import time
from gi.repository import GLib, Gtk

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
import hawkey
import json
import logging
import operator
import sys

VERSION = 104  # (00.01.02) must be integer

FAKE_ATTR = ['downgrades', 'action', 'pkgtags', 'changelog']
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
    '''
    Dnf Download callback handler class
    '''
    def __init__(self):
        pass

    def downloadStart(self, num_files, num_bytes):
        ''' Starting a new parallel download batch '''
        self.DownloadStart(num_files, num_bytes)  # send a signal

    def downloadProgress(self, name, frac, total_frac, total_files):
        ''' Progress for a single instance in the batch '''
        # send a signal
        self.DownloadProgress(name, frac, total_frac, total_files)

    def downloadEnd(self, name, status, msg):
        ''' Download of af single instace ended '''
        if not status:
            status = -1
        if not msg:
            msg = ""
        self.DownloadEnd(name, status, msg)  # send a signal

    def repoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
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

    def _get_obsoletes(self):
        ''' Cache a list of obsoletes'''
        if not self._obsoletes_list:
            self._obsoletes_list = list(self.base.packages.obsoletes)
        return self._obsoletes_list

    @property
    def base(self):
        '''
        yumbase property so we can auto initialize it if not defined
        '''
        if not self._base:
            self._get_base()
        return self._base

#=========================================================================
# Helper methods for api methods both in system & session
# Search -> search etc
#=========================================================================

    def search_with_attr(self, fields, keys, attrs, match_all, newest_only,
                          tags):
        '''
        Search for for packages, where given fields contain given key words
        (Helper for Search)

        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param attrs: list of extra attributes to get
        :param match_all: match all flag, if True return only packages
                          matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags
        '''
        # FIXME: Add support for search in pkgtags, when supported in dnf
        showdups = not newest_only
        pkgs = self.base.search(fields, keys, match_all, showdups)
        values = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(values)

    def expire_cache(self):
        try:
            self.base.expire_cache()
            self.base.reset(sack=True)
            self.base.setup_base()
            return True
        except dnf.exceptions.RepoError as e:
            self.logger.error(str(e))
            self.ErrorMessage(str(e))
            return False

    def _get_po_by_name(self, name, newest_only):
        '''
        Get packages matching a name pattern

        :param name: name pattern
        :param newest_only: True = get newest packages only
        '''
        subj = dnf.subject.Subject(name)
        qa = subj.get_best_query(self.base.sack, with_provides=False)
        if newest_only:
            qa = qa.latest()
        pkgs = self.base.packages.filter_packages(qa)
        return pkgs

    def _find_group(self, pattern):
        """ Find comps.Group object by pattern"""
        if not self.base.comps:  # lazy load the comps metadata
            self.base.read_comps()
        grp = self.base.comps.group_by_pattern(pattern)
        return grp

    def get_groups(self):
        '''
        make a list with categoties and there groups
        This is the old way of yum groups, where a group is a collection of
        mandatory, default and optional pacakges and the group
        is installed when all mandatory & default packages is installed.
        '''
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
        '''
        Get the value a list of repo ids
        :param filter: filter to limit the listed repositories
        '''
        if filter == '' or filter == 'enabled':
            repos = [repo.id for repo in self.base.repos.iter_enabled()]
        else:
            repos = [repo.id for repo in self.base.repos.get_matching(filter)]
        return repos

    def get_config(self, setting):
        '''
        Get the value of a yum config setting
        it will return a JSON string of the config
        :param setting: name of setting (debuglevel etc..)
        '''
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
        '''
        Get information about a give repo_id
        the repo setting will be returned as dictionary in JSON format
        :param repo_id:
        '''
        value = json.dumps(None)
        repo = self.base.repos.get(repo_id, None)  # get the repo object
        if repo:
            repo_conf = dict([(c, getattr(repo, c)) for c in repo.iterkeys()])
            value = json.dumps(repo_conf)
        return value

    def set_enabled_repos(self, repo_ids):
        '''
        Enable a list of repos, disable the ones not in list
        '''
        self._reset_base()
        self._get_base(reset=True, load_sack=False)
        for repo in self.base.repos.all():
            if repo.id in repo_ids:
                logger.debug("  enabled : %s ", repo.id)
                repo.enable()
            else:
                repo.disable()
        self._base.setup_base()  # load the sack with the current enabled repos

    def get_packages(self, pkg_filter):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        '''
        if pkg_filter in ['installed', 'available', 'updates', 'obsoletes',
                          'recent', 'extras']:
            pkgs = getattr(self.base.packages, pkg_filter)
            value = self._to_package_id_list(pkgs)
        else:
            value = []
        return value

    def get_packages_with_attributes(self, pkg_filter, fields):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        '''
        value = []
        if pkg_filter in ['installed', 'available', 'updates', 'obsoletes',
                          'recent', 'extras']:
            pkgs = getattr(self.base.packages, pkg_filter)
            value = [self._get_po_list(po, fields) for po in pkgs]
        return json.dumps(value)

    def get_attribute(self, id, attr):
        '''
        Get an attribute from a yum package id
        it will return a python repr string of the attribute
        :param id: yum package id
        :param attr: name of attribute (summary, size, description,
                     changelog etc..)
        '''
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

    def _get_installed_na(self, name, arch):
        q = self.base.sack.query()
        inst = q.installed().filter(name=name, arch=arch).run()
        if inst:
            return inst[0]
        else:
            return None

    def get_updateInfo(self, id):
        '''
        Get an Update Infomation e from a dnf package id
        it will return a python repr string of the attribute
        :param id: dnf package id
        '''
        po = self._get_po(id)
        if po:
            # TODO : updateinfo is not supported in DNF yet
            # https://bugzilla.redhat.com/show_bug.cgi?id=850912
            value = json.dumps(None)
        else:
            value = json.dumps(None)
        return value

    def get_packages_by_name_with_attr(self, name, attrs, newest_only):
        """
        get packages matching a name wildcard with extra attributes
        """
        pkgs = self._get_po_by_name(name, newest_only)
        values = [self._get_po_list(po, attrs) for po in pkgs]
        return json.dumps(values)

    def get_group_pkgs(self, grp_id, grp_flt, fields):
        '''
        Get packages for a given grp_id and group filter
        '''
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
        value = [self._get_po_list(po, fields) for po in pkgs]
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
        self.base.reset(goal=True)  # reset the current goal

    def get_transaction(self):
        value = json.dumps(self._get_transaction_list())
        return value

    def build_transaction(self):
        '''
        Resolve dependencies of current transaction
        '''
        self.TransactionEvent('start-build', NONE)
        value = json.dumps(self._get_transaction_list())
        self.TransactionEvent('end-build', NONE)
        return value

    def _get_packages_to_download(self):
        to_dnl = []
        for tsi in self.base.transaction:
            if tsi.installed:
                to_dnl.append(tsi.installed)
        return to_dnl

    def run_transaction(self, max_err):
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
        '''
        Get the yum history transaction member located in a date interval
        from today
        :param start: start days from today
        :param end: end days from today
        '''
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
        '''
        search in yum history
        :param pattern: list of search patterns
        :type pattern: list
        '''
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
        '''
        return a list of (pkg_id, tx_state, installed_state) pairs from a given
        yum history transaction id
        '''
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

    def _get_transaction_list(self):
        '''
        Generate a list of the current transaction
        '''
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

    def _to_transaction_id_list(self):
        '''
        return a sorted list of package ids from a list of packages
        if and po is installed, the installed po id will be returned
        :param pkgs:
        '''
        result = []
        for tsi in self.base.transaction:
            po = tsi.active
            result.append("%s,%s" %
                          (self._get_id(po), tsi.active_history_state))
        return result

    def _set_option(self, option, value):
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
        '''
        Callback for handling af user confirmation of gpg key import

        :param gpg_info: dict with info about gpg key
        {"po": ..,  "userid": .., "hexkeyid": .., "keyurl": ..,
          "fingerprint": .., "timestamp": ..)

        '''
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

    def _get_po_list(self, po, attrs):
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
        '''
        return a list of (tid, isodate) pairs from a list of
        yum history transactions
        '''
        result = []
        for ht in hist_trans:
            tm = datetime.fromtimestamp(ht.end_timestamp)
            result.append((ht.tid, tm.isoformat()))
        return result

    def _get_fake_attributes(self, po, attr):
        '''
        Get Fake Attributes, a whey to useful stuff for a package
        there is not real attritbutes to the yum package object.
        :param attr: Fake attribute
        :type attr: string
        '''
        if attr == "action":
            return self._get_action(po)
        elif attr == 'downgrades':
            return self._get_downgrades(po)
        elif attr == 'pkgtags':
            return self._get_pkgtags(po)
        elif attr == 'changelog':
            # TODO : changelog is not supported in DNF yet
            # https://bugzilla.redhat.com/show_bug.cgi?id=1066867
            return None

    def _get_downgrades(self, pkg):
        pkg_ids = []
        ''' Find available downgrades for a given name.arch'''
        q = self.base.sack.query()
        avail = q.available().filter(name=pkg.name, arch=pkg.arch).run()
        for apkg in avail:
            if pkg.evr_gt(apkg):
                pkg_ids.append(self._get_id(apkg))
        return pkg_ids

    def _get_pkgtags(self, po):
        '''
        Get pkgtags from a given po
        '''
        # TODO : pkgtags is not supported in DNF yet
        return []

    def _to_package_id_list(self, pkgs):
        '''
        return a sorted list of package ids from a list of packages
        if and po is installed, the installed po id will be returned
        :param pkgs:
        '''
        result = set()
        for po in sorted(pkgs):
            result.add(self._get_id(po))
        return result

    def _get_po(self, id):
        ''' find the real package from an package id'''
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
        '''
        convert a yum package obejct to an id string containing
        (n,e,v,r,a,repo)
        :param pkg:
        '''
        values = [
            pkg.name, str(pkg.epoch), pkg.version, pkg.release,
            pkg.arch, pkg.ui_from_repo]
        return ",".join(values)

    def _get_action(self, po):
        '''
        Return the available action for a given pkg_id
        The action is what can be performed on the package
        an installed package will return as 'remove' as action
        an available update will return 'update'
        an available package will return 'install'
        :param po: yum package
        :type po: yum package object
        :return: action (remove, install, update, downgrade, obsolete)
        :rtype: string
        '''
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
        '''
        Get a Dnf Base object to work with
        '''
        if not self._base or reset:
            self._base = DnfBase(self)
            if load_sack:
                self._base.setup_base()
        return self._base

    def _reset_base(self):
        '''
        destroy the current DnfBase object
        '''
        if self._base:
            self._base.close()
            self._base = None

    def _setup_watchdog(self):
        '''
        Setup the watchdog to run every second when idle
        '''
        GLib.timeout_add(1000, self._watchdog)

    def _watchdog(self):
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
                Gtk.main_quit()
        else:
            self._watchdog_count += 1
            self.logger.debug("Watchdog : %i" % self._watchdog_count)
            return True

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
        print("error: %s" % msg)
        pass


class Packages:

    def __init__(self, base):
        self._base = base
        self._sack = base.sack
        self._inst_na = self._sack.query().installed().na_dict()

    def filter_packages(self, pkg_list, replace=True):
        '''
        Filter a list of package objects and replace
        the installed ones with the installed object, instead
        of the available object
        '''
        pkgs = set()
        for pkg in pkg_list:
            key = (pkg.name, pkg.arch)
            inst_pkg = self._inst_na.get(key, [None])[0]
            if inst_pkg and inst_pkg.evr == pkg.evr:
                if replace:
                    pkgs.add(inst_pkg)
            else:
                pkgs.add(pkg)
        return list(pkgs)

    @property
    def query(self):
        return self._sack.query()

    @property
    def installed(self):
        '''
        instawlled packages
        '''
        return self.query.installed().run()

    @property
    def updates(self):
        '''
        available updates
        '''
        return self.query.upgrades().run()

    @property
    def all(self, showdups=False):
        '''
        all packages in the repositories
        installed ones are replace with the install package objects
        '''
        if showdups:
            return self.filter_packages(self.query.available().run())
        else:
            return self.filter_packages(self.query.latest().run())

    @property
    def available(self, showdups=False):
        '''
        available packages there is not installed yet
        '''
        if showdups:
            return self.filter_packages(self.query.available().run(),
                                        replace=False)
        else:
            return self.filter_packages(self.query.available().latest().run(),
                                        replace=False)

    @property
    def extras(self):
        '''
        installed packages, not in current repos
        '''
        # anything installed but not in a repo is an extra
        avail_dict = self.query.available().pkgtup_dict()
        inst_dict = self.query.installed().pkgtup_dict()
        pkgs = []
        for pkgtup in inst_dict:
            if pkgtup not in avail_dict:
                pkgs.extend(inst_dict[pkgtup])
        return pkgs

    @property
    def obsoletes(self):
        '''
        packages there is obsoleting some installed packages
        '''
        inst = self.query.installed()
        return self.query.filter(obsoletes=inst)

    @property
    def recent(self, showdups=False):
        recent = []
        now = time()
        recentlimit = now - (self._base.conf.recent * 86400)
        if showdups:
            avail = self.query.available()
        else:
            avail = self.query.latest()
        for po in avail:
            if int(po.buildtime) > recentlimit:
                recent.append(po)
        return recent


class DnfBase(dnf.Base):

    def __init__(self, parent):
        super(DnfBase, self).__init__()
        self.parent = parent
        self.md_progress = MDProgress(parent)
        self.setup_cache()
        self.read_all_repos()
        self.progress = Progress(parent, max_err=100)
        self.repos.all().set_progress_bar(self.md_progress)
        self._packages = None

    def expire_cache(self):
        self.cleanExpireCache()  # FIXME : cleanExpireCache() is not public API

    def setup_base(self):
        self.fill_sack()
        self._packages = Packages(self)

    @property
    def packages(self):
        return self._packages

    def setup_cache(self):
        # perform the CLI-specific cachedir tricks
        conf = self.conf
        conf.releasever = None  # This will take the current release
        # FIXME: This is not public API, but we want the same cache as dnf cli
        suffix = dnf.yum.parser.varReplace(
            dnf.const.CACHEDIR_SUFFIX, conf.yumvar)
        cli_cache = dnf.conf.CliCache(conf.cachedir, suffix)
        conf.cachedir = cli_cache.cachedir
        self._system_cachedir = cli_cache.system_cachedir
        logger.debug("dnf cachedir: %s" % conf.cachedir)

    def set_max_error(self, max_err):
        """
        Setup a new progress object with a new max number of download errors
        """
        self.progress = Progress(self.parent, max_err=max_err)

    def search(self, fields, values, match_all=True, showdups=False):
        '''
        search in a list of package fields for a list of keys
        :param fields: package attributes to search in
        :param values: the values to match
        :param match_all: match all values (default)
        :param showdups: show duplicate packages or latest (default)
        :return: a list of package objects
        '''
        matches = set()
        for key in values:
            key_set = set()
            for attr in fields:
                pkgs = set(self.contains(attr, key).run())
                key_set |= pkgs
            if len(matches) == 0:
                matches = key_set
            else:
                if match_all:
                    matches &= key_set
                else:
                    matches |= key_set
        result = list(matches)
        if not showdups:
            result = self.sack.query().filter(pkg=result).latest().run()
        return result

    def contains(self, attr, needle, ignore_case=True):
        fdict = {'%s__substr' % attr: needle}
        if ignore_case:
            return self.sack.query().filter(hawkey.ICASE, **fdict)
        else:
            return self.sack.query().filter(**fdict)


class MDProgress(dnf.callback.DownloadProgress):

    def __init__(self, parent):
        super(MDProgress, self).__init__()
        self._last = -1.0
        self.parent = parent

    def start(self, total_files, total_size):
        self._last = -1.0

    def end(self, payload, status, msg):
        name = str(payload)
        if status == dnf.callback.STATUS_OK:
            self.parent.repoMetaDataProgress(name, 1.0)

    def progress(self, payload, done):
        name = str(payload)
        cur_total_bytes = payload.download_size
        if cur_total_bytes:
            frac = done / float(cur_total_bytes)
        else:
            frac = 0.0
        if frac > self._last + 0.01:
            self._last = frac
            self.parent.repoMetaDataProgress(name, frac)


class Progress(dnf.callback.DownloadProgress):

    def __init__(self, parent, max_err):
        super(Progress, self).__init__()
        self.parent = parent
        self.max_err = max_err
        self.total_files = 0
        self.total_size = 0.0
        self.download_files = 0
        self.download_size = 0.0
        self._dnl_errors = {}
        self._err_count = 0
        self.dnl = {}
        self.last_frac = 0

    def start(self, total_files, total_size):
        self.total_files = total_files
        self.total_size = float(total_size)
        self.download_files = 0
        self.download_size = 0.0
        self.parent.downloadStart(total_files, total_size)

    def end(self, payload, status, msg):
        # payload download complete
        if status in [dnf.callback.STATUS_OK,
                      dnf.callback.STATUS_ALREADY_EXISTS]:
            self.download_files += 1
        else:
            pload = str(payload)
            if pload in self._dnl_errors:
                self._dnl_errors[pload].append(msg)
            else:
                self._dnl_errors[pload] = [msg]
            self._err_count += 1
            if self._err_count > self.max_err:
                raise DownloadError(self._dnl_errors)
        self.parent.downloadEnd(str(payload), status, msg)

    def progress(self, payload, done):
        pload = str(payload)
        cur_total_bytes = payload.download_size
        if not pload in self.dnl:
            self.dnl[pload] = 0.0
        else:
            self.dnl[pload] = done
        total_frac = self.get_total()
        if total_frac > self.last_frac:
            self.last_frac = total_frac
            if cur_total_bytes:
                frac = done / cur_total_bytes
            else:
                frac = 0.0
            self.parent.downloadProgress(
                pload, frac, total_frac, self.download_files)

    def get_total(self):
        """ Get the total downloaded percentage"""
        tot = 0.0
        for value in self.dnl.values():
            tot += value
        frac = tot / self.total_size
        return frac

    def update(self):
        """ Output the current progress"""

        sys.stdout.write("Progress : %-3d %% (%d/%d)\r" %
                         (self.last_pct,
                          self.download_files,
                          self.total_files))


def doTextLoggerSetup(logroot='dnfdaemon', logfmt='%(asctime)s: %(message)s',
                      loglvl=logging.INFO):
    ''' Setup Python logging  '''
    logger = logging.getLogger(logroot)
    logger.setLevel(loglvl)
    formatter = logging.Formatter(logfmt, "%H:%M:%S")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.propagate = False
    logger.addHandler(handler)
