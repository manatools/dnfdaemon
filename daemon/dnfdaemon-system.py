#!/usr/bin/python3
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

# (C) 2013-2014 Tim Lauridsen <timlau@fedoraproject.org>

#
# dnf system  bus dBus service

# FIXME: Hack for gobject don't blow up'
import os
os.environ['XDG_RUNTIME_DIR'] = '/root'

from dnfdaemon.server import Logger

import argparse
import dbus
import dbus.service
import dbus.mainloop.glib
import dnfdaemon.server
import logging

DAEMON_ORG = 'org.baseurl.DnfSystem'
DAEMON_INTERFACE = DAEMON_ORG
logger = logging.getLogger('dnfdaemon.system')


#--------------------------------------------------------------- DBus Exception
class AccessDeniedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG + '.AccessDeniedError'


class LockedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG + '.LockedError'


class TransactionError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG + '.TransactionError'


class NotImplementedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG + '.NotImplementedError'


#------------------------------------------------------------ Callback handlers

class DnfDaemon(dnfdaemon.server.DnfDaemonBase):

    def __init__(self):
        dnfdaemon.server.DnfDaemonBase.__init__(self)
        bus_name = dbus.service.BusName(DAEMON_ORG, bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/')
        logger.debug('Starting %s: API Version : %d', DAEMON_ORG,
                                              dnfdaemon.server.API_VERSION)

#=========================================================================
# DBus Methods
#=========================================================================

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='i')
    def GetVersion(self):
        """
        Get the daemon version
        """
        return dnfdaemon.server.API_VERSION

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='b',
                         sender_keyword='sender')
    def Exit(self, sender=None):
        """
        Exit the daemon
        :param sender:
        """
        self.check_permission_read(sender)
        if self._can_quit:
            self._reset_base()
            self.mainloop_quit()
            return True
        else:
            return False

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='b',
                         sender_keyword='sender')
    def Lock(self, sender=None):
        """
        Get the dnfdaemon lock
        :param sender:
        """
        self.check_permission_read(sender)
        if not self._lock:
            self._lock = sender
            logger.info('LOCK: Locked by : %s' % sender)
            return True
        return False

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='b',
                         out_signature='b',
                         sender_keyword='sender')
    def SetWatchdogState(self, state, sender=None):
        """
        Set the Watchdog state
        :param state: True = Watchdog active, False = Watchdog disabled
        :type state: boolean (b)
        """
        self.check_permission_read(sender)
        self._watchdog_disabled = not state
        return state

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='as',
                         sender_keyword='sender')
    def GetRepositories(self, filter, sender=None):
        """
        Get the value a list of repo ids
        :param filter: filter to limit the listed repositories
        :param sender:
        """
        self.working_start(sender, write=False)
        repos = self.get_repositories(filter)
        return self.working_ended(repos)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='as',
                         out_signature='',
                         sender_keyword='sender')
    def SetEnabledRepos(self, repo_ids, sender=None):
        """
        Enabled a list of repositories, disabled all other repos
        :param repo_ids: list of repo ids to enable
        :param sender:
        """
        self.working_start(sender, write=False)
        self.set_enabled_repos(repo_ids)
        return self.working_ended()

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='b',
                         sender_keyword='sender')
    def ExpireCache(self, sender=None):
        """
        Enabled a list of repositories, disabled all other repos
        :param repo_ids: list of repo ids to enable
        :param sender:
        :return: True if cache is populated without errors
        """
        self.working_start(sender, write=False)
        rc = self.expire_cache()
        return self.working_ended(rc)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def GetConfig(self, setting, sender=None):
        """
        Get the value of a yum config setting
        it will return a JSON string of the config
        :param setting: name of setting (debuglevel etc..)
        :param sender:
        """
        self.working_start(sender, write=False)
        value = self.get_config(setting)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='ss',
                         out_signature='b',
                         sender_keyword='sender')
    def SetConfig(self, setting, value, sender=None):
        """
        Set yum config setting for the running session
        :param setting: yum conf setting to set
        :param value: value to set
        :param sender:
        """
        self.working_start(sender, write=False)
        rc = self.set_option(setting, value)
        return self.working_ended(rc)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def GetRepo(self, repo_id, sender=None):
        """
        Get information about a give repo_id
        the repo setting will be returned as dictionary in JSON format
        :param repo_id:
        :param sender:
        """
        self.working_start(sender, write=False)
        value = self.get_repo(repo_id)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='sas',
                         out_signature='s',
                         sender_keyword='sender')
    def GetPackages(self, pkg_filter, fields, sender=None):
        """
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        :param sender:
        """
        self.working_start(sender, write=False)
        if fields ==  ['summary', 'size', 'group']:
            value = self.get_packages_ndsg(pkg_filter)
        else:
            value = self.get_packages(pkg_filter, fields)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='sasb',
                         out_signature='s',
                         sender_keyword='sender')
    def GetPackagesByName(self, name, attrs, newest_only, sender=None):
        """
        Get a list of packages from a name pattern
        :param name: name pattern
        :param newest_only: True = get newest packages only
        :param attrs: list of package attributes to get
        :param sender:
        """
        self.working_start(sender, write=False)
        values = self.get_packages_by_name_with_attr(name, attrs, newest_only)
        return self.working_ended(values)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='ss',
                         out_signature='s',
                         sender_keyword='sender')
    def GetAttribute(self, pkg_id, attr, sender=None):
        """
        Get an attribute from a yum package pkg_id
        it will return a python repr string of the attribute
        :param pkg_id: yum package pkg_id
        :param attr: name of attribute (summary, size, description,
                     changelog etc..)
        :param sender:
        """
        self.working_start(sender, write=False)
        value = self.get_attribute(pkg_id, attr)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='i',
                         out_signature='s',
                         sender_keyword='sender')
    def GetHistoryPackages(self, tid, sender=None):
        """
        Get packages from a given yum history transaction id

        :param tid: history transaction id
        :type tid: integer
        :return: list of (pkg_id, state, installed) pairs
        :rtype: json encoded string
        """
        self.working_start(sender, write=False)
        value = self.get_history_transaction_pkgs(tid)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='i',
                         out_signature='s',
                         sender_keyword='sender')
    def HistoryUndo(self, tid, sender=None):
        """Undo history from a given yum history transaction id.

        tid: history transaction id
        """
        self.working_start(sender, write=False)
        value = self.history_undo(tid)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='ii',
                         out_signature='s',
                         sender_keyword='sender')
    def GetHistoryByDays(self, start_days, end_days, sender=None):
        """
        Get History transaction in a interval of days from today

        :param start_days: start of interval in days from now (0 = today)
        :type start_days: integer
        :param end_days:end of interval in days from now
        :type end_days: integer
        :return: a list of (transaction is, date-time) pairs
        :type sender: json encoded string
        """
        self.working_start(sender, write=False)
        value = self.get_history_by_days(start_days, end_days)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='as',
                         out_signature='s',
                         sender_keyword='sender')
    def HistorySearch(self, pattern, sender=None):
        """
        Search the history for transaction matching a pattern
        :param pattern: patterne to match
        :type pattern: string
        :return: list of (tid,isodates)
        :type sender: json encoded string
        """
        self.working_start(sender, write=False)
        value = self.history_search(pattern)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='b',
                         sender_keyword='sender')
    def Unlock(self, sender=None):
        """ release the lock"""
        self.check_permission_read(sender)
        if self.check_lock(sender):
            self._reset_base()
            logger.info('UNLOCK: Lock Release by %s' % self._lock)
            self._lock = None
            return True

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def GroupInstall(self, cmds, sender=None):
        """
        Install groups based on command patterns separated by spaces
        sinulate what 'dnf group install <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.group_install(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def GroupRemove(self, cmds, sender=None):
        """
        Install groups based on command patterns separated by spaces
        sinulate what 'dnf group install <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.group_remove(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def Install(self, cmds, sender=None):
        """
        Install packages based on command patterns separated by spaces
        sinulate what 'yum install <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.install(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def Remove(self, cmds, sender=None):
        """
        Remove packages based on command patterns separated by spaces
        sinulate what 'yum remove <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.remove(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def Update(self, cmds, sender=None):
        """
        Update packages based on command patterns separated by spaces
        sinulate what 'yum update <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.update(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def Reinstall(self, cmds, sender=None):
        """
        Reinstall packages based on command patterns separated by spaces
        sinulate what 'yum reinstall <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.reinstall(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='s',
                         out_signature='s',
                         sender_keyword='sender')
    def Downgrade(self, cmds, sender=None):
        """
        Downgrade packages based on command patterns separated by spaces
        sinulate what 'yum downgrade <arguments>' does
        :param cmds: command patterns separated by spaces
        :param sender:
        """
        self.working_start(sender)
        value = self.downgrade(cmds)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='ss',
                         out_signature='s',
                         sender_keyword='sender')
    def AddTransaction(self, pkg_id, action, sender=None):
        """
        Add an package to the current transaction

        :param pkg_id: package pkg_id for the package to add
        :param action: the action to perform ( install, update, remove,
                       obsolete, reinstall, downgrade, localinstall )
        """
        self.working_start(sender, write=False)
        value = self.add_transaction(pkg_id, action)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='',
                         sender_keyword='sender')
    def ClearTransaction(self, sender):
        """
        Clear the transactopm
        """
        self.working_start(sender, write=False)
        self.clear_transaction()
        return self.working_ended()

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='s',
                         sender_keyword='sender')
    def GetTransaction(self, sender=None):
        """
        Return the members of the current transaction
        """
        self.working_start(sender, write=False)
        value = self.get_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='s',
                         sender_keyword='sender')
    def BuildTransaction(self, sender):
        """
        Resolve dependencies of current transaction
        """
        self.working_start(sender, write=False)
        value = self.build_transaction()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='s',
                         sender_keyword='sender')
    def RunTransaction(self, sender=None):
        """Run the current yum transaction."""
        self.working_start(sender)
        self.check_permission_write(sender)
        self.check_lock(sender)
        result = self.run_transaction()
        return self.working_ended(result)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='asasasbbb',
                         out_signature='s',
                         sender_keyword='sender')
    def Search(self, fields, keys, attrs, match_all, newest_only,
               tags, sender=None):
        """
        Search for for packages, where given fields contain given key words
        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param attrs: list of extra attributes to get
        :param match_all: match all flag, if True return only packages
                          matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags
        """
        self.working_start(sender, write=False)
        result = self.search_with_attr(
            fields, keys, attrs, match_all, newest_only, tags)
        return self.working_ended(result)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='',
                         out_signature='s',
                         sender_keyword='sender')
    def GetGroups(self, sender=None):
        """
        Return a category/group tree
        """
        self.working_start(sender, write=False)
        value = self.get_groups()
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='ssas',
                         out_signature='s',
                         sender_keyword='sender')
    def GetGroupPackages(self, grp_id, grp_flt, fields, sender=None):
        """
        Get packages in a group by grp_id and grp_flt
        :param grp_id: The Group id
        :param grp_flt: Group Filter (all or default)
        :param fields: list of package attributes to include in list
        :param sender:
        """
        self.working_start(sender, write=False)
        value = self.get_group_pkgs(grp_id, grp_flt, fields)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                         in_signature='sb',
                         out_signature='',
                         sender_keyword='sender')
    def ConfirmGPGImport(self, hexkeyid, confirmed, sender=None):
        """
        Confirm import of at GPG Key by yum
        :param hexkeyid: hex keyid for GPG key
        :param confirmed: confirm import of key (True/False)
        :param sender:
        """

        self.working_start(sender)
        # store confirmation of GPG import
        self._gpg_confirm[hexkeyid] = confirmed
        return self.working_ended()

#=========================================================================
# DBus signals
#=========================================================================
# Parallel Download Progress signals
    @dbus.service.signal(DAEMON_INTERFACE)
    def ErrorMessage(self, error_msg):
        """ Send an error message """
        pass

    @dbus.service.signal(DAEMON_INTERFACE, signature='uu')
    def DownloadStart(self, num_files, num_bytes):
        """ Starting a new parallel download batch """
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def DownloadProgress(self, name, frac, total_frac, total_files):
        """ Progress for a single instance in the batch """
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def DownloadEnd(self, name, status, msg):
        """ Download of af single instace ended """
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def RepoMetaDataProgress(self, name, frac):
        """ Repository Metadata Download progress """

    @dbus.service.signal(DAEMON_INTERFACE)
    def TransactionEvent(self, event, data):
        """
        DBus signal with Transaction event information, telling the current
        step in the processing of the current transaction.

        Steps are : start-run, download, pkg-to-download, signature-check,
                    run-test-transaction,
        run-transaction, verify, fail, end-run

        :param event: current step
        """
        # print "event: %s" % event
        pass

    @dbus.service.signal(DAEMON_INTERFACE)
    def RPMProgress(self, package, action, te_current, te_total, ts_current,
                    ts_total):
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
    def GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        """
        GPG Key Import DBus signal

        :param pkg_id: pkg_id for the package needing the GPG Key
                       to be verified
        :param userid: GPG key name
        :param hexkeyid: GPG key hex id
        :param keyurl: Url to the GPG Key
        :param timestamp:
        """
        pass

#=========================================================================
# Helper methods
#=========================================================================
    def working_start(self, sender, write=True):
        if write:
            self.check_permission_write(sender)
        else:
            self.check_permission_read(sender)
        self.check_lock(sender)
        self._is_working = True
        self._watchdog_count = 0

    def working_ended(self, value=None):
        self._is_working = False
        return value

    def check_lock(self, sender):
        """
        Check that the current sender is owning the dnfdaemon lock
        :param sender:
        """
        if self._lock == sender:
            return True
        elif self._lock:
            raise LockedError('dnfdaemon is locked by another application')
        else:
            raise LockedError('dnfdaemon is not locked, but was expected to be')

    def check_permission_write(self, sender):
        """ Check for senders permission to update system packages"""
        if sender in self.authorized_sender_write:
            return
        else:
            self._check_permission(sender, 'org.baseurl.DnfSystem.write')
            self.authorized_sender_write.add(sender)

    def check_permission_read(self, sender):
        """ Check for senders permission to read system packages"""
        if sender in self.authorized_sender_read:
            return
        else:
            self._check_permission(sender, 'org.baseurl.DnfSystem.read')
            self.authorized_sender_read.add(sender)

    def _check_permission(self, sender, action):
        """ Check senders permissions using PolicyKit1
        """
        if not sender:
            raise ValueError('sender == None')

        obj = dbus.SystemBus().get_object(
            'org.freedesktop.PolicyKit1',
            '/org/freedesktop/PolicyKit1/Authority')
        obj = dbus.Interface(obj, 'org.freedesktop.PolicyKit1.Authority')
        (granted, _, details) = obj.CheckAuthorization(
            ('system-bus-name', {'name': sender}), action, {},
            dbus.UInt32(1), '', timeout=600)
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
            dnfdaemon.server.doTextLoggerSetup(logroot='dnfdaemon',
                loglvl=logging.DEBUG)
        else:
            dnfdaemon.server.doTextLoggerSetup(logroot='dnfdaemon')

    # setup the DBus mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    yd = DnfDaemon()
    if not args.notimeout:
        yd._setup_watchdog()
    yd.mainloop_run()


if __name__ == '__main__':
    main()
