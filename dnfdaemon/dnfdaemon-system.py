#!/usr/bin/python -tt
#coding: utf-8
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# (C) 2013 - Tim Lauridsen <timlau@fedoraproject.org>

#
# dnf session bus dBus service (Readonly)
#

from __future__ import print_function
from __future__ import absolute_import
import dbus
import dbus.service
import dbus.glib
import gobject
import json
import logging
import operator

import argparse

import dnf.transaction
from dnf.exceptions import PackagesNotInstalledError, DownloadError, MarkingError

from common import DnfDaemonBase, doTextLoggerSetup, Logger, NONE

version = 101 #  (00.01.01) must be integer
DAEMON_ORG = 'org.baseurl.DnfSystem'
DAEMON_INTERFACE = DAEMON_ORG

def _(msg):
    return msg

_ACTIVE_DCT = {
    dnf.transaction.DOWNGRADE : operator.attrgetter('installed'),
    dnf.transaction.ERASE : operator.attrgetter('erased'),
    dnf.transaction.INSTALL : operator.attrgetter('installed'),
    dnf.transaction.REINSTALL : operator.attrgetter('installed'),
    dnf.transaction.UPGRADE : operator.attrgetter('installed'),
    }
def _active_pkg(tsi):
    """Return the package from tsi that takes the active role in the transaction.
    """
    return _ACTIVE_DCT[tsi.op_type](tsi)


#------------------------------------------------------------------------------ DBus Exception
class AccessDeniedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.AccessDeniedError'

class LockedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.LockedError'

class YumTransactionError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.TransactionError'

class NotImplementedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.NotImplementedError'

#------------------------------------------------------------------------------ Callback handlers


class DaemonBase():

    def __init__(self, daemon):
        self._daemon = daemon

    def _checkSignatures(self,pkgs,callback):
        ''' The the signatures of the downloaded packages '''
        return 0


logger = logging.getLogger('dnfdaemon')

#------------------------------------------------------------------------------ Main class
class DnfDaemon(DnfDaemonBase):

    def __init__(self, mainloop):
        DnfDaemonBase.__init__(self,  mainloop)
        self.logger = logging.getLogger('dnfdaemon.system')
        bus_name = dbus.service.BusName(DAEMON_ORG, bus = dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/')
        self._gpg_confirm = {}

#===============================================================================
# DBus Methods
#===============================================================================

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='i')
    def GetVersion(self):
        '''
        Get the daemon version
        '''
        return version

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='b',
                                          sender_keyword='sender')
    def Exit(self, sender=None):
        '''
        Exit the daemon
        :param sender:
        '''
        self.check_permission(sender)
        if self._can_quit:
            self._reset_base()
            self.mainloop.quit()
            return True
        else:
            return False

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='b',
                                          sender_keyword='sender')
    def Lock(self, sender=None):
        '''
        Get the yum lock
        :param sender:
        '''
        self.check_permission(sender)
        if not self._lock:
            self._lock = sender
            self.logger.info('LOCK: Locked by : %s' % sender)
            return True
        return False

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='b',
                                          out_signature='b',
                                          sender_keyword='sender')
    def SetWatchdogState(self,state, sender=None):
        '''
        Set the Watchdog state
        :param state: True = Watchdog active, False = Watchdog disabled
        :type state: boolean (b)
        '''
        self.check_permission(sender)
        self._watchdog_disabled = not state
        return state


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='as',
                                          sender_keyword='sender')

    def GetRepositories(self, filter, sender=None):
        '''
        Get the value a list of repo ids
        :param filter: filter to limit the listed repositories
        :param sender:
        '''
        self.working_start(sender)
        repos = self._get_repositories(filter)
        return self.working_ended(repos)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='as',
                                          out_signature='',
                                          sender_keyword='sender')

    def SetEnabledRepos(self, repo_ids, sender=None):
        '''
        Enabled a list of repositories, disabled all other repos
        :param repo_ids: list of repo ids to enable
        :param sender:
        '''
        self.working_start(sender)
        self._set_enabled_repos(repo_ids)
        return self.working_ended()


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetConfig(self, setting ,sender=None):
        '''
        Get the value of a yum config setting
        it will return a JSON string of the config
        :param setting: name of setting (debuglevel etc..)
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_config(setting)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='ss',
                                          out_signature='b',
                                          sender_keyword='sender')
    def SetConfig(self, setting, value ,sender=None):
        '''
        Set yum config setting for the running session
        :param setting: yum conf setting to set
        :param value: value to set
        :param sender:
        '''
        self.working_start(sender)
        rc = self._set_option(setting, json.loads(value))
        return self.working_ended(rc)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetRepo(self, repo_id ,sender=None):
        '''
        Get information about a give repo_id
        the repo setting will be returned as dictionary in JSON format
        :param repo_id:
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_repo(repo_id)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='as',
                                          sender_keyword='sender')
    def GetPackages(self, pkg_filter, sender=None):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_packages(pkg_filter)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='sas',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetPackageWithAttributes(self, pkg_filter, fields, sender=None):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_package_with_attributes(pkg_filter, fields)
        return self.working_ended(json.dumps(value))

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='sb',
                                          out_signature='as',
                                          sender_keyword='sender')
    def GetPackagesByName(self, name, newest_only, sender=None):
        '''
        Get a list of packages from a name pattern
        :param name: name pattern
        :param newest_only: True = get newest packages only
        :param sender:
        '''
        self.working_start(sender)
        pkg_ids = self._get_packages_by_name(name, newest_only)
        return self.working_ended(pkg_ids)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='ss',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetAttribute(self, pkg_id, attr,sender=None):
        '''
        Get an attribute from a yum package pkg_id
        it will return a python repr string of the attribute
        :param pkg_id: yum package pkg_id
        :param attr: name of attribute (summary, size, description, changelog etc..)
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_attribute( pkg_id, attr)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetUpdateInfo(self, pkg_id,sender=None):
        '''
        Get an Update Infomation e from a yum package pkg_id
        it will return a python repr string of the attribute
        :param pkg_id: yum package pkg_id
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_updateInfo(pkg_id)
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='i',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetHistoryPackages(self, tid,sender=None):
        '''
        Get packages from a given yum history transaction id

        :param tid: history transaction id
        :type tid: integer
        :return: list of (pkg_id, state, installed) pairs
        :rtype: json encoded string
        '''
        self.working_start(sender)
        value = json.dumps(self._get_history_transaction_pkgs(tid))
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='ii',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetHistoryByDays(self, start_days, end_days ,sender=None):
        '''
        Get History transaction in a interval of days from today

        :param start_days: start of interval in days from now (0 = today)
        :type start_days: integer
        :param end_days:end of interval in days from now
        :type end_days: integer
        :return: a list of (transaction is, date-time) pairs
        :type sender: json encoded string
        '''
        self.working_start(sender)
        value = json.dumps(self._get_history_by_days(start_days, end_days))
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='as',
                                          out_signature='s',
                                          sender_keyword='sender')
    def HistorySearch(self, pattern ,sender=None):
        '''
        Search the history for transaction matching a pattern
        :param pattern: patterne to match
        :type pattern: string
        :return: list of (tid,isodates)
        :type sender: json encoded string
        '''
        self.working_start(sender)
        value = json.dumps(self._history_search(pattern))
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='b',
                                          sender_keyword='sender')
    def Unlock(self, sender=None):
        ''' release the lock'''
        self.check_permission(sender)
        if self.check_lock(sender):
            self._reset_base()
            self.logger.info('UNLOCK: Lock Release by %s' % self._lock)
            self._lock = None
            return True

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def Install(self, cmds, sender=None):
        '''
        Install packages based on command patterns separated by spaces
        sinulate what 'yum install <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        '''
        self.working_start(sender)
        value = 0
        for cmd in cmds.split(' '):
            if cmd.endswith('.rpm'):
                self.base.install_local(cmd)
            else:
                try:
                    self.base.install(cmd)
                except MarkingError:
                    pass
        value = self._build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def Remove(self, cmds, sender=None):
        '''
        Remove packages based on command patterns separated by spaces
        sinulate what 'yum remove <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        '''
        self.working_start(sender)
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.remove(cmd)
        except PackagesNotInstalledError: # ignore if the package is not installed
            pass
        value = self._build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def Update(self, cmds, sender=None):
        '''
        Update packages based on command patterns separated by spaces
        sinulate what 'yum update <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        '''
        self.working_start(sender)
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.upgrade(cmd)
        except PackagesNotInstalledError: # ignore if the package is not installed
            pass
        value = self._build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def Reinstall(self, cmds, sender=None):
        '''
        Reinstall packages based on command patterns separated by spaces
        sinulate what 'yum reinstall <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        '''
        self.working_start(sender)
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.reinstall(cmd)
        except PackagesNotInstalledError: # ignore if the package is not installed
            pass
        value = self._build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def Downgrade(self, cmds, sender=None):
        '''
        Downgrade packages based on command patterns separated by spaces
        sinulate what 'yum downgrade <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        '''
        self.working_start(sender)
        value = 0
        try:
            for cmd in cmds.split(' '):
                self.base.downgrade(cmd)
        except PackagesNotInstalledError: # ignore if the package is not installed
            pass
        value = self._build_transaction()
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='ss',
                                          out_signature='s',
                                          sender_keyword='sender')

    def AddTransaction(self, pkg_id, action, sender=None):
        '''
        Add an package to the current transaction

        :param pkg_id: package pkg_id for the package to add
        :param action: the action to perform ( install, update, remove, obsolete, reinstall, downgrade, localinstall )
        '''
        self.working_start(sender)
        value = None
        if action != "localinstall": # localinstall has the path to the local rpm, not pkg_id
            po = self._get_po(pkg_id)
        # FIXME: missing dnf API of adding to hawkey.Goal object
        # no easy way to add to the hawkey.Sack object in dnf
        # using public api
        # filed upstream bug
        # https://bugzilla.redhat.com/show_bug.cgi?id=1073859
        print(action,str(po))
        try:
            if action == 'install':
                self.base.install(str(po),reponame=po.reponame) # FIXME: reponame is not public api
            elif action == 'remove':
                self.base.remove(str(po)) # FIXME: reponame is not public api
            elif action == 'update':
                self.base.upgrade(str(po),reponame=po.reponame) # FIXME: reponame is not public api
            elif action == 'obsolete':
                self.base.obsolete(str(po),reponame=po.reponame) # FIXME: reponame is not public api
            elif action == 'reinstall':
                self.base.reinstall(str(po),reponame=po.reponame) # FIXME: reponame is not public api
            elif action == 'downgrade':
                self.base.downgtade(str(po),reponame=po.reponame) # FIXME: reponame is not public api
            elif action == 'localinstall':
                self.base.install_local(pkg_id) # FIXME: install_local is not public api
        except PackagesNotInstalledError: # ignore if the package is not installed
            pass
        # FIXME: No public api to list the current hawkey.goal
        # so we depsolve and return the current transaction
        value = self._build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='',
                                          sender_keyword='sender')
    def ClearTransaction(self, sender):
        '''
        Clear the transactopm
        '''
        self.working_start(sender)
        self.base.reset(goal = True) # reset the current goal
        self._build_transaction() # desolve empty goal, to clean the transaction obj.
        return self.working_ended()


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='s',
                                          sender_keyword='sender')

    def GetTransaction(self, sender=None):
        '''
        Return the members of the current transaction
        '''
        self.working_start(sender)
        # FIXME: We sould return the current hawkey.goal not the transaction
        # because the transaction is not populated before the depsolve.
        value = json.dumps(self._get_transaction_list())
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='s',
                                          sender_keyword='sender')
    def BuildTransaction(self, sender):
        '''
        Resolve dependencies of current transaction
        '''
        self.working_start(sender)
        value = self._build_transaction()
        return self.working_ended(value)


    def _build_transaction(self):
        '''
        Resolve dependencies of current transaction
        '''
        self.TransactionEvent('start-build',NONE)
        rc = self.base.resolve()
        if rc: # OK
            output = self._get_transaction_list()
        else:
            output = []
        self.TransactionEvent('end-build',NONE)
        return json.dumps((rc,output))

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='i',
                                          sender_keyword='sender')
    def RunTransaction(self, sender = None):
        '''
        Run the current yum transaction
        '''
        self.working_start(sender)
        self.check_permission(sender)
        self.check_lock(sender)
        self.TransactionEvent('start-run',NONE)
        self._can_quit = False
        to_dnl = self._get_packages_to_download()
        try:
            if to_dnl:
                self.base.download_packages(to_dnl, self.base.progress)
            rc, msgs = self.base.do_transaction()
        except DownloadError as e:
            print("download error : ", str(e))
        self._can_quit = True
        self._reset_base()
        self.TransactionEvent('end-run',NONE)
        return self.working_ended(rc)

    def _get_packages_to_download(self):
        to_dnl = []
        for tsi in self.base.transaction:
            if tsi.installed:
                to_dnl.append(tsi.installed)
        return to_dnl

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='asasbbb',
                                          out_signature='as',
                                          sender_keyword='sender')
    def Search(self, fields, keys, match_all, newest_only, tags, sender=None ):
        '''
        Search for for packages, where given fields contain given key words
        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param match_all: match all flag, if True return only packages matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags

        '''
        self.working_start(sender)
        result = self._search(fields, keys, match_all, newest_only, tags)
        return self.working_ended(result)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetGroups(self, sender=None ):
        '''
        Return a category/group tree
        '''
        self.working_start(sender)
        value = self._get_groups()
        return self.working_ended(value)


    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='ss',
                                          out_signature='as',
                                          sender_keyword='sender')
    def GetGroupPackages(self, grp_id, grp_flt, sender=None ):
        '''
        Get packages in a group by grp_id and grp_flt
        :param grp_id: The Group id
        :param grp_flt: Group Filter (all or default)
        :param sender:
        '''
        self.working_start(sender)
        pkg_ids = self._get_group_pkgs(grp_id, grp_flt)
        return self.working_ended(pkg_ids)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='sb',
                                          out_signature='',
                                          sender_keyword='sender')
    def ConfirmGPGImport(self, hexkeyid, confirmed, sender=None ):
        '''
        Confirm import of at GPG Key by yum
        :param hexkeyid: hex keyid for GPG key
        :param confirmed: confirm import of key (True/False)
        :param sender:
        '''

        self.working_start(sender)
        self._gpg_confirm[hexkeyid] = confirmed # store confirmation of GPG import
        return self.working_ended()


#
#  Template for new method
#
#    @dbus.service.method(DAEMON_INTERFACE,
#                                          in_signature='',
#                                          out_signature='',
#                                          sender_keyword='sender')
#    def NewMethod(self, sender=None ):
#        '''
#
#        '''
#        self.working_start(sender)
#        value = True
#        return self.working_ended(value)
#


#===============================================================================
# DBus signals
#===============================================================================
# Parallel Download Progress signals

    @dbus.service.signal(DAEMON_INTERFACE)
    def DownloadStart(self, num_files, num_bytes):
        ''' Starting a new parallel download batch '''
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def DownloadProgress(self, name, frac, total_frac, total_files):
        ''' Progress for a single instance in the batch '''
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def DownloadEnd(self, name, status, msg):
        ''' Download of af single instace ended '''
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''


    @dbus.service.signal(DAEMON_INTERFACE)
    def TransactionEvent(self,event,data):
        '''
        DBus signal with Transaction event information, telling the current step in the processing of
        the current transaction.

        Steps are : start-run, download, pkg-to-download, signature-check, run-test-transaction, run-transaction, fail, end-run

        :param event: current step
        '''
        #print "event: %s" % event
        pass


    @dbus.service.signal(DAEMON_INTERFACE)
    def RPMProgress(self, package, action, te_current, te_total, ts_current, ts_total):
        """
        RPM Progress DBus signal
        :param package: A yum package object or simple string of a package name
        :param action: A yum.constant transaction set state or in the obscure
                       rpm repackage case it could be the string 'repackaging'
        :param te_current: Current number of bytes processed in the transaction
                           element being processed
        :param te_total: Total number of bytes in the transaction element being
                         processed
        :param ts_current: number of processes completed in whole transaction
        :param ts_total: total number of processes in the transaction.
        """
        pass


    @dbus.service.signal(DAEMON_INTERFACE)
    def GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp ):
        '''
        GPG Key Import DBus signal

        :param pkg_id: pkg_id for the package needing the GPG Key to be verified
        :param userid: GPG key name
        :param hexkeyid: GPG key hex id
        :param keyurl: Url to the GPG Key
        :param timestamp:
        '''
        pass

#===============================================================================
# Helper methods
#===============================================================================
    def working_start(self,sender):
        self.check_permission(sender)
        self.check_lock(sender)
        self._is_working = True
        self._watchdog_count = 0

    def working_ended(self, value=None):
        self._is_working = False
        return value

    def handle_gpg_import(self, gpg_info):
        '''
        Callback for handling af user confirmation of gpg key import

        :param gpg_info: dict with info about gpg key {"po": ..,  "userid": .., "hexkeyid": .., "keyurl": ..,  "fingerprint": .., "timestamp": ..)

        '''
        print(gpg_info)
        pkg_id = self._get_id(gpg_info['po'])
        userid = gpg_info['userid']
        hexkeyid = gpg_info['hexkeyid']
        keyurl = gpg_info['keyurl']
        #fingerprint = gpg_info['fingerprint']
        timestamp = gpg_info['timestamp']
        if not hexkeyid in self._gpg_confirm: # the gpg key has not been confirmed by the user
            self._gpg_confirm[hexkeyid] = False
            self.GPGImport( pkg_id, userid, hexkeyid, keyurl, timestamp )
        return self._gpg_confirm[hexkeyid]


    def _set_option(self, option, value):
        if hasattr(self.base.conf, option):
            setattr(self.base.conf, option, value)
            self.logger.debug(_("Setting Option %s = %s") % (option, value))
            for repo in self.base.repos.iter_enabled():
                if hasattr(repo, option):
                    setattr(repo, option, value)
                    self.logger.debug("Setting Option %s = %s (%s)" % (option, value, repo.id), __name__)
            return True
        else:
            return False
        pass


    def _get_history_by_days(self, start, end):
        '''
        Get the yum history transaction member located in a date interval from today
        :param start: start days from today
        :param end: end days from today
        '''
        result = []
        # TODO : Add dnf code (_get_history_by_days)
        return self._get_id_time_list(result)

    def _history_search(self, pattern):
        '''
        search in yum history
        :param pattern: list of search patterns
        :type pattern: list
        '''
        result = []
        # TODO : Add dnf code (_history_search)
        return self._get_id_time_list(result)

    def _get_history_transaction_pkgs(self, tid):
        '''
        return a list of (pkg_id, tx_state, installed_state) pairs from a given
        yum history transaction id
        '''
        result = []
        # TODO : Add dnf code (_get_history_transaction_pkgs)
        return result

    def _get_transaction_list(self):
        '''
        Generate a list of the current transaction
        '''
        out_list = []
        sublist = []
        tx_list = self._make_trans_dict()
        for (action, pkglist) in [('install', tx_list['install']),
                            ('update', tx_list['update']),
                            ('remove', tx_list['remove']),
                            ('reinstall', tx_list['reinstall']),
                            ('downgrade', tx_list['downgrade'])]:

            for tsi in pkglist:
                po = _active_pkg(tsi)
                (n, a, e, v, r) = po.pkgtup
                size = float(po.size)
                alist = []
                # TODO : Add support for showing package replacement
                el = (self._get_id(po), size, alist)
                sublist.append(el)
            if pkglist:
                out_list.append([action, sublist])
                sublist = []
        return out_list

    def _make_trans_dict(self):
        b = {}
        for t in ('downgrade', 'remove', 'install', 'reinstall', 'update'):
            b[t] = []
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
        return b



    def _to_transaction_id_list(self):
        '''
        return a sorted list of package ids from a list of packages
        if and po is installed, the installed po id will be returned
        :param pkgs:
        '''
        result = []
        for tsi in self.base.transaction:
            po = tsi.active
            result.append("%s,%s" % (self._get_id(po), tsi.active_history_state ))
        return result

    def check_lock(self, sender):
        '''
        Check that the current sender is owning the yum lock
        :param sender:
        '''
        if self._lock == sender:
            return True
        else:
            raise LockedError('dnf is locked by another application')


    def check_permission(self, sender):
        ''' Check for senders permission to run root stuff'''
        if sender in self.authorized_sender:
            return
        else:
            self._check_permission(sender)
            self.authorized_sender.add(sender)


    def _check_permission(self, sender):
        '''
        check senders permissions using PolicyKit1
        :param sender:
        '''
        if not sender: raise ValueError('sender == None')

        obj = dbus.SystemBus().get_object('org.freedesktop.PolicyKit1', '/org/freedesktop/PolicyKit1/Authority')
        obj = dbus.Interface(obj, 'org.freedesktop.PolicyKit1.Authority')
        (granted, _, details) = obj.CheckAuthorization(
                ('system-bus-name', {'name': sender}), DAEMON_ORG, {}, dbus.UInt32(1), '', timeout=600)
        if not granted:
            raise AccessDeniedError('Session is not authorized')


def main():
    parser = argparse.ArgumentParser(description='Dnf D-Bus Daemon')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('--notimeout', action='store_true')
    args = parser.parse_args()
    if args.verbose:
        if args.debug:
            doTextLoggerSetup(logroot='dnfdaemon',loglvl=logging.DEBUG)
        else:
            doTextLoggerSetup(logroot='dnfdaemon')

    # setup the DBus mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    mainloop = gobject.MainLoop()
    yd = DnfDaemon(mainloop)
    if not args.notimeout:
        yd._setup_watchdog()
    mainloop.run()

if __name__ == '__main__':
    main()
