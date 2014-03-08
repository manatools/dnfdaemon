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

import argparse

import sys
import os

from common import DnfDaemonBase, doTextLoggerSetup, Logger, DownloadCallback, FAKE_ATTR, NONE, \
                   TransactionDisplay

version = 902 #  (00.09.02) must be integer
DAEMON_ORG = 'org.baseurl.DnfSession'
DAEMON_INTERFACE = DAEMON_ORG
FAKE_ATTR = ['downgrades','action','pkgtags']
NONE = json.dumps(None)

def _(msg):
    return msg

#------------------------------------------------------------------------------ DBus Exception
class AccessDeniedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.AccessDeniedError'

class LockedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.LockedError'

class NotImplementedError(dbus.DBusException):
    _dbus_error_name = DAEMON_ORG+'.NotImplementedError'


logger = logging.getLogger('dnfdaemon.session')

#------------------------------------------------------------------------------ Main class
class DnfDaemon(DnfDaemonBase):

    def __init__(self, mainloop):
        DnfDaemonBase.__init__(self,  mainloop)
        self.logger = logging.getLogger('dnfdaemon-session')
        bus_name = dbus.service.BusName(DAEMON_ORG, bus = dbus.SessionBus())
        dbus.service.Object.__init__(self, bus_name, '/')

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
        if self._can_quit:
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
        #  TODO : Add dnf code
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
    def GetAttribute(self, id, attr,sender=None):
        '''
        Get an attribute from a yum package id
        it will return a python repr string of the attribute
        :param id: yum package id
        :param attr: name of attribute (summary, size, description, changelog etc..)
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_attribute( id, attr)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='s',
                                          out_signature='s',
                                          sender_keyword='sender')
    def GetUpdateInfo(self, id,sender=None):
        '''
        Get an Update Infomation e from a yum package id
        it will return a python repr string of the attribute
        :param id: yum package id
        :param sender:
        '''
        self.working_start(sender)
        value = self._get_updateInfo(id)
        return self.working_ended(value)

    @Logger
    @dbus.service.method(DAEMON_INTERFACE,
                                          in_signature='',
                                          out_signature='b',
                                          sender_keyword='sender')
    def Unlock(self, sender=None):
        ''' release the lock'''
        if self.check_lock(sender):
            #  TODO : Add dnf code
            self.logger.info('UNLOCK: Lock Release by %s' % self._lock)
            self._lock = None
            return True

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
    @dbus.service.signal(DAEMON_INTERFACE)
    def UpdateProgress(self,name,frac,fread,ftime):
        '''
        DBus signal with download progress information
        will send dbus signals with download progress information
        :param name: filename
        :param frac: Progress fracment (0 -> 1)
        :param fread: formated string containing BytesRead
        :param ftime : formated string containing remaining or elapsed time
        '''
        pass

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


#===============================================================================
# Helper methods
#===============================================================================
    def working_start(self,sender):
        self.check_lock(sender)
        self._is_working = True
        self._watchdog_count = 0

    def working_ended(self, value=None):
        self._is_working = False
        return value

    def check_lock(self, sender):
        '''
        Check that the current sender is owning the yum lock
        :param sender:
        '''
        if self._lock == sender:
            return True
        else:
            raise LockedError('dnf is locked by another application')



def main():
    parser = argparse.ArgumentParser(description='Yum D-Bus Session Daemon')
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
