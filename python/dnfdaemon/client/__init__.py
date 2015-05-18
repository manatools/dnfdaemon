# coding: utf-8
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
This is a Python 2.x & 3.x client API for the dnf-daemon Dbus Service

This module gives a simple pythonic interface to doing  package action
using the dnf-daemon Dbus service.

It use async call to the dnf-daemon, so signal can be catched and a Gtk gui do
not get unresonsive

There is 2 classes :class:`DnfDaemonClient` & :class:`DnfDaemonReadOnlyClient`

:class:`DnfDaemonClient` uses a system DBus service running as root and
can make chages to the system.

:class:`DnfDaemonReadOnlyClient` uses a session DBus service running as
current user and can only do readonly actions.

Usage: (Make your own subclass based on :class:`dnfdaemon.DnfDaemonClient`
and overload the signal handlers)::


    from dnfdaemon import DnfDaemonClient

    class MyClient(DnfDaemonClient):

        def __init(self):
            DnfDaemonClient.__init__(self)
            # Do your stuff here

        def on_TransactionEvent(self,event, data):
            # Do your stuff here
            pass

        def on_RPMProgress(self, package, action, te_current, te_total,
                           ts_current, ts_total):
            # Do your stuff here
            pass

        def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl,  timestamp ):
           # do stuff here
           pass

        def on_DownloadStart(self, num_files, num_bytes):
            ''' Starting a new parallel download batch '''
           # do stuff here
           pass

        def on_DownloadProgress(self, name, frac, total_frac, total_files):
            ''' Progress for a single instance in the batch '''
           # do stuff here
           pass

        def on_DownloadEnd(self, name, status, msg):
            ''' Download of af single instace ended '''
           # do stuff here
           pass

        def on_RepoMetaDataProgress(self, name, frac):
            ''' Repository Metadata Download progress '''
           # do stuff here
           pass


Usage: (Make your own subclass based on
:class:`dnfdaemon.DnfDaemonReadOnlyClient` and overload the signal handlers)::


    from dnfdaemon import DnfDaemonReadOnlyClient

    class MyClient(DnfDaemonReadOnlyClient):

        def __init(self):
            DnfDaemonClient.__init__(self)
            # Do your stuff here

        def on_RepoMetaDataProgress(self, name, frac):
            ''' Repository Metadata Download progress '''
           # do stuff here
           pass

"""

import json
import sys
import re
import weakref
import logging

__VERSION__ = "0.3.4"

logger = logging.getLogger("dnfdaemon.client")

from gi.repository import Gio, GObject, GLib

ORG = 'org.baseurl.DnfSystem'
INTERFACE = ORG

ORG_READONLY = 'org.baseurl.DnfSession'
INTERFACE_READONLY = ORG_READONLY

DBUS_ERR_RE = re.compile('.*GDBus.Error:([\w\.]*): (.*)$')

#
# Exceptions
#


class DaemonError(Exception):
    'Error from the backend'


class AccessDeniedError(DaemonError):
    'User press cancel button in policykit window'


class LockedError(DaemonError):
    'The Yum daemon is locked'


class TransactionError(DaemonError):
    'The yum transaction failed'

#
# Helper Classes
#


class DBus:
    '''Helper class to work with GDBus in a easier way
    '''
    def __init__(self, conn):
        self.conn = conn

    def get(self, bus, obj, iface=None):
        if iface is None:
            iface = bus
        return Gio.DBusProxy.new_sync(
            self.conn, 0, None, bus, obj, iface, None
        )

    def get_async(self, callback, bus, obj, iface=None):
        if iface is None:
            iface = bus
        Gio.DBusProxy.new(
            self.conn, 0, None, bus, obj, iface, None, callback, None
        )


class WeakMethod:
    ''' Helper class to work with a weakref class method '''
    def __init__(self, inst, method):
        self.proxy = weakref.proxy(inst)
        self.method = method

    def __call__(self, *args):
        return getattr(self.proxy, self.method)(*args)


# Get the system bus
system = DBus(Gio.bus_get_sync(Gio.BusType.SYSTEM, None))
session = DBus(Gio.bus_get_sync(Gio.BusType.SESSION, None))

#
# Main Client Class
#


class DnfDaemonBase:

    def __init__(self, bus, org, interface):
        self.bus = bus
        self.dbus_org = org
        self.dbus_interface = interface
        self.daemon = self._get_daemon(bus, org, interface)
        logger.debug("%s daemon loaded - version :  %s" %
                     (interface, self.daemon.GetVersion()))

    def _get_daemon(self, bus, org, interface):
        ''' Get the daemon dbus proxy object'''
        try:
            proxy = bus.get(org, "/", interface)
            proxy.GetVersion()  # Get daemon version, to check if it is alive
            # Connect the Dbus signal handler
            proxy.connect('g-signal', WeakMethod(self, '_on_g_signal'))
            return proxy
        except Exception as err:
            self._handle_dbus_error(err)

    def _on_g_signal(self, proxy, sender, signal, params):
        '''DBUS signal Handler '''
        args = params.unpack()  # unpack the glib variant
        self.handle_dbus_signals(proxy, sender, signal, args)

    def handle_dbus_signals(self, proxy, sender, signal, args):
        """ Overload in child class """
        pass

    def _handle_dbus_error(self, err):
        '''Parse error from service and raise python Exceptions
        '''
        exc, msg = self._parse_error()
        if exc != "":
            logger.error("Exception   : %s", exc)
            logger.error("   message  : %s", msg)
        if exc == self.dbus_org + '.AccessDeniedError':
            raise AccessDeniedError(msg)
        elif exc == self.dbus_org + '.LockedError':
            raise LockedError(msg)
        elif exc == self.dbus_org + '.TransactionError':
            raise TransactionError(msg)
        elif exc == self.dbus_org + '.NotImplementedError':
            raise TransactionError(msg)
        else:
            raise DaemonError(str(err))

    def _parse_error(self):
        '''parse values from a DBus releated exception '''
        (type, value, traceback) = sys.exc_info()
        res = DBUS_ERR_RE.match(str(value))
        if res:
            return res.groups()
        return "", ""

    def _return_handler(self, obj, result, user_data):
        '''Async DBus call, return handler '''
        if isinstance(result, Exception):
            # print(result)
            user_data['result'] = None
            user_data['error'] = result
        else:
            user_data['result'] = result
            user_data['error'] = None
        user_data['main_loop'].quit()

    def _get_result(self, user_data):
        '''Get return data from async call or handle error

        user_data:
        '''
        if user_data['error']:  # Errors
            self._handle_dbus_error(user_data['error'])
        else:
            return user_data['result']

    def _run_dbus_async(self, cmd, *args):
        '''Make an async call to a DBus method in the yumdaemon service

        cmd: method to run
        '''
        main_loop = GLib.MainLoop()
        data = {'main_loop': main_loop}
        func = getattr(self.daemon, cmd)
        # timeout = infinite
        func(*args, result_handler=self._return_handler,
             user_data=data, timeout=GObject.G_MAXINT)
        data['main_loop'].run()
        result = self._get_result(data)
        return result

    def _run_dbus_sync(self, cmd, *args):
        '''Make a sync call to a DBus method in the yumdaemon service
        cmd:
        '''
        func = getattr(self.daemon, cmd)
        return func(*args)

#
# Dbus Signal Handlers (Overload in child class)
#

    def on_TransactionEvent(self, event, data):
        print("TransactionEvent : %s" % event)
        if data:
            print("Data :\n", data)

    def on_RPMProgress(
            self, package, action, te_current, te_total, ts_current, ts_total):
        print("RPMProgress : %s %s" % (action, package))

    def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        values = (pkg_id, userid, hexkeyid, keyurl, timestamp)
        print("on_GPGImport : %s" % (repr(values)))

    def on_DownloadStart(self, num_files, num_bytes):
        ''' Starting a new parallel download batch '''
        values = (num_files, num_bytes)
        print("on_DownloadStart : %s" % (repr(values)))

    def on_DownloadProgress(self, name, frac, total_frac, total_files):
        ''' Progress for a single instance in the batch '''
        values = (name, frac, total_frac, total_files)
        print("on_DownloadProgress : %s" % (repr(values)))

    def on_DownloadEnd(self, name, status, msg):
        ''' Download of af single instace ended '''
        values = (name, status, msg)
        print("on_DownloadEnd : %s" % (repr(values)))

    def on_RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        values = (name, frac)
        print("on_RepoMetaDataProgress : %s" % (repr(values)))

    def on_ErrorMessage(self, msg):
        ''' Error message from daemon service '''
        print("on_ErrorMessage : %s" % (msg))

#
# API Methods
#

    def Lock(self):
        '''Get the yum lock, this give exclusive access to the daemon and yum
        this must always be called before doing other actions
        '''
        try:
            return self._run_dbus_async('Lock')
        except Exception as err:
            self._handle_dbus_error(err)

    def Unlock(self):
        '''Release the yum lock '''
        try:
            self.daemon.Unlock()
        except Exception as err:
            self._handle_dbus_error(err)

    def SetWatchdogState(self, state):
        '''Set the Watchdog state

        Args:
            state: True = Watchdog active, False = Watchdog disabled
        '''
        try:
            self.daemon.SetWatchdogState("(b)", state)
        except Exception as err:
            self._handle_dbus_error(err)

    def GetPackages(self, pkg_filter, fields=[]):
        '''Get a list of pkg list for a given package filter

        each pkg list contains [pkg_id, field,....] where field is a
        atrribute of the package object
        Ex. summary, size etc.

        Args:
            pkg_filter: package filter ('installed','available',
                               'updates','obsoletes','recent','extras')
            fields: yum package objects attributes to get.
        '''
        result = self._run_dbus_async(
            'GetPackages', '(sas)', pkg_filter, fields)
        return json.loads(result)

    def ExpireCache(self):
        '''Expire the dnf metadata, so they will be refresed'''
        rc = self._run_dbus_async('ExpireCache', '()')
        return rc

    def GetRepositories(self, repo_filter):
        '''Get a list of repository ids where name matches a filter

        Args:
            repo_filter: filter to match

        Returns:
            list of repo id's
        '''
        result = self._run_dbus_async('GetRepositories', '(s)', repo_filter)
        return [str(r) for r in result]

    def GetRepo(self, repo_id):
        '''Get a dictionary of information about a given repo id.

        Args:
            repo_id: repo id to get information from

        Returns:
            dictionary with repo info
        '''
        result = json.loads(self._run_dbus_async('GetRepo', '(s)', repo_id))
        return result

    def SetEnabledRepos(self, repo_ids):
        '''Enabled a list of repositories, disabled all other repos

        Args:
            repo_ids: list of repo ids to enable
        '''
        self._run_dbus_async('SetEnabledRepos', '(as)', repo_ids)

    def GetConfig(self, setting):
        '''Read a config setting from yum.conf

        Args:
            setting: setting to read
        '''
        result = json.loads(self._run_dbus_async('GetConfig', '(s)', setting))
        return result

    def GetAttribute(self, pkg_id, attr):
        '''Get yum package attribute (description, filelist, changelog etc)

        Args:
            pkg_id: pkg_id to get attribute from
            attr: name of attribute to get
        '''
        result = self._run_dbus_async('GetAttribute', '(ss)', pkg_id, attr)
        if result == ':none':  # illegal attribute
            result = None
        elif result == ':not_found':  # package not found
            result = None  # FIXME: maybe raise an exception
        else:
            result = json.loads(result)
        return result

    def GetPackagesByName(self, name, attr=[], newest_only=True):
        '''Get a list of pkg ids for starts with name

        Args:
            name: name prefix to match
            attr: a list of packages attributes to return (optional)
            newest_only: show only the newest match or every
                                match (optinal).

        Returns:
            list of [pkg_id, attr1, attr2, ...]
        '''
        return json.loads(self._run_dbus_async('GetPackagesByName', '(sasb)',
                          name, attr, newest_only))

    def GetGroups(self):
        '''Get list of Groups. '''
        return json.loads(self._run_dbus_async('GetGroups'))

    def GetGroupPackages(self, grp_id, grp_flt, fields):
        '''Get packages in a group

        Args:
            grp_id: the group id to get packages for
            grp_flt: the filter ('all' = all packages ,
                     'default' = packages to be installed, before
                     the group is installed)
            fields: extra package attributes to include in result
        '''
        return json.loads(self._run_dbus_async('GetGroupPackages', '(ssas)',
                          grp_id, grp_flt, fields))

    def Search(self, fields, keys, attrs, match_all, newest_only, tags):
        '''Search for packages where keys is matched in fields

        Args:
            fields: yum po attributes to search in
            keys: keys to search for
            attrs: list of extra package attributes to get
            match_all: match all keys or only one
            newest_only: return only the newest version of packages
            tags: search pkgtags

        Returns:
            list of pkg_id's
        '''
        return json.loads(self._run_dbus_async('Search', '(asasasbbb)',
                          fields, keys, attrs, match_all, newest_only, tags))

    def Exit(self):
        '''End the daemon'''
        self._run_dbus_async('Exit')

#
# Helper methods
#

    def to_pkg_tuple(self, id):
        ''' split the pkg_id into a tuple'''
        (n, e, v, r, a, repo_id) = str(id).split(',')
        return (n, e, v, r, a, repo_id)

    def to_txmbr_tuple(self, id):
        ''' split the txmbr_id into a tuple'''
        (n, e, v, r, a, repo_id, ts_state) = str(id).split(',')
        return (n, e, v, r, a, repo_id, ts_state)


class ClientReadOnly(DnfDaemonBase):
    '''A class to communicate with the yumdaemon DBus services in a easy way
    '''

    def __init__(self):
        DnfDaemonBase.__init__(self, session, ORG_READONLY, INTERFACE_READONLY)

    def handle_dbus_signals(self, proxy, sender, signal, args):
        ''' DBUS signal Handler '''
        if signal == "RepoMetaDataProgress":
            self.on_RepoMetaDataProgress(*args)
        else:
            print("Unhandled Signal : " + signal, " Param: ", args)


class Client(DnfDaemonBase):
    '''A class to communicate with the yumdaemon DBus services in a easy way
    '''

    def __init__(self):
        DnfDaemonBase.__init__(self, system, ORG, INTERFACE)

    def handle_dbus_signals(self, proxy, sender, signal, args):
        ''' DBUS signal Handler '''
        if signal == "TransactionEvent":
            self.on_TransactionEvent(*args)
        elif signal == "RPMProgress":
            self.on_RPMProgress(*args)
        elif signal == "GPGImport":
            self.on_GPGImport(*args)
        elif signal == "DownloadStart":
            self.on_DownloadStart(*args)
        elif signal == "DownloadEnd":
            self.on_DownloadEnd(*args)
        elif signal == "DownloadProgress":
            self.on_DownloadProgress(*args)
        elif signal == "RepoMetaDataProgress":
            self.on_RepoMetaDataProgress(*args)
        elif signal == "ErrorMessage":
            self.on_ErrorMessage(*args)
        else:
            print("Unhandled Signal : " + signal, " Param: ", args)

#
# API Methods
#

    def SetConfig(self, setting, value):
        '''Set a dnf config setting

        Args:
            setting: yum conf setting to set
            value: value to set
        '''
        result = self._run_dbus_async(
            'SetConfig', '(ss)', setting, json.dumps(value))
        return result

    def ClearTransaction(self):
        '''Clear the current transaction. '''
        return self._run_dbus_async('ClearTransaction')

    def GetTransaction(self):
        '''Get the current transaction

        Returns:
            the current transaction
        '''
        return json.loads(self._run_dbus_async('GetTransaction'))

    def AddTransaction(self, id, action):
        '''Add an package to the current transaction

        Args:
            id: package id for the package to add
            action: the action to perform ( install, update, remove,
                    obsolete, reinstall, downgrade, localinstall )
        '''
        return json.loads(self._run_dbus_async('AddTransaction', '(ss)',
                          id, action))

    def GroupInstall(self, pattern):
        '''Do a group install <pattern string>,
        same as dnf group install <pattern string>

        Args:
            pattern: group pattern to install
       '''
        return json.loads(self._run_dbus_async('GroupInstall', '(s)', pattern))

    def GroupRemove(self, pattern):
        '''
        Do a group remove <pattern string>,
        same as dnf group remove <pattern string>

        Args:
            pattern: group pattern to remove
       '''
        return json.loads(self._run_dbus_async('GroupRemove', '(s)', pattern))

    def Install(self, pattern):
        '''Do a install <pattern string>,
        same as dnf install <pattern string>

        Args:
            pattern: package pattern to install
       '''
        return json.loads(self._run_dbus_async('Install', '(s)', pattern))

    def Remove(self, pattern):
        '''Do a install <pattern string>,
        same as dnf remove <pattern string>

        Args:
            pattern: package pattern to remove
        '''
        return json.loads(self._run_dbus_async('Remove', '(s)', pattern))

    def Update(self, pattern):
        '''Do a update <pattern string>,
        same as dnf update <pattern string>

        Args:
            pattern: package pattern to update

        '''
        return json.loads(self._run_dbus_async('Update', '(s)', pattern))

    def Reinstall(self, pattern):
        '''Do a reinstall <pattern string>,
        same as dnf reinstall <pattern string>

        Args:
            pattern: package pattern to reinstall

        '''
        return json.loads(self._run_dbus_async('Reinstall', '(s)', pattern))

    def Downgrade(self, pattern):
        '''Do a install <pattern string>, same as yum remove <pattern string>

        Args:
            pattern: package pattern to downgrade
        '''
        return json.loads(self._run_dbus_async('Downgrade', '(s)', pattern))

    def BuildTransaction(self):
        '''Get a list of pkg ids for the current availabe updates '''
        return json.loads(self._run_dbus_async('BuildTransaction'))

    def RunTransaction(self, max_err=100):
        ''' Get a list of pkg ids for the current availabe updates

        Args:
            max_err: maximun number of download error before we bail out
        '''
        return json.loads(self._run_dbus_async('RunTransaction', '(i)',
                          max_err))

    def GetHistoryByDays(self, start_days, end_days):
        '''Get History transaction in a interval of days from today

        Args:
            start_days: start of interval in days from now (0 = today)
            end_days:end of interval in days from now

        Returns:
            list of (transaction is, date-time) pairs
        '''
        value = self._run_dbus_async(
            'GetHistoryByDays', '(ii)', start_days, end_days)
        return json.loads(value)

    def HistorySearch(self, pattern):
        '''Search the history for transaction matching a pattern

        Args:
            pattern: patterne to match

        Returns:
            list of (tid,isodates)
        '''
        value = self._run_dbus_async('HistorySearch', '(as)', pattern)
        return json.loads(value)

    def GetHistoryPackages(self, tid):
        '''Get packages from a given yum history transaction id

        Args:
            tid: history transaction id

        Returns:
            list of (pkg_id, state, installed) pairs
        '''
        value = self._run_dbus_async('GetHistoryPackages', '(i)', tid)
        return json.loads(value)

    def HistoryUndo(self, tid):
        """Undo a given dnf history transaction id

        Args:
            tid: history transaction id

        Returns:
            (rc, messages)
        """
        value = self._run_dbus_async('HistoryUndo', '(i)', tid)
        return json.loads(value)

    def ConfirmGPGImport(self, hexkeyid, confirmed):
        '''Confirm import of at GPG Key by yum

        Args:
            hexkeyid: hex keyid for GPG key
            confirmed: confirm import of key (True/False)
        '''
        self._run_dbus_async('ConfirmGPGImport', '(si)', hexkeyid, confirmed)
