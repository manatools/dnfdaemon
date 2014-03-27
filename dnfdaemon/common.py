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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# (C) 2013 - Tim Lauridsen <timlau@fedoraproject.org>

"""
Common stuff for the dnfdaemon dbus services
"""
from __future__ import print_function
from __future__ import absolute_import
import dbus
import dbus.service
import dbus.glib
import json
import logging
from datetime import datetime
from time import time
from gi.repository import GLib, Gtk


import sys

import dnf
import dnf.yum
import dnf.const
import dnf.conf
import dnf.subject
import dnf.callback
import hawkey
from dnf.exceptions import DownloadError

FAKE_ATTR = ['downgrades','action','pkgtags','changelog']
NONE = json.dumps(None)


#------------------------------------------------------------------------------ Callback handlers

logger = logging.getLogger('dnfdaemon.service')

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

class DownloadCallback:
    '''
    Dnf Download callback handler class
    '''
    def __init__(self):
        pass

    def downloadStart(self, num_files, num_bytes):
        ''' Starting a new parallel download batch '''
        self.DownloadStart(num_files, num_bytes) # send a signal

    def downloadProgress(self, name, frac, total_frac, total_files):
        ''' Progress for a single instance in the batch '''
        self.DownloadProgress(name, frac, total_frac, total_files) # send a signal

    def downloadEnd(self, name, status, msg):
        ''' Download of af single instace ended '''
        if not status:
            status = -1
        if not msg:
            msg = ""
        self.DownloadEnd(name, status, msg) # send a signal

    def repoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        self.RepoMetaDataProgress( name, frac)



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
        self._timeout_idle = 20         # time to daemon is closed when unlocked
        self._timeout_locked = 600      # time to daemon is closed when locked and not working
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

#===============================================================================
# Helper methods for api methods both in system & session
# Search -> _search etc
#===============================================================================


    def _search(self, fields, keys, match_all, newest_only, tags):
        '''
        Search for for packages, where given fields contain given key words
        (Helper for Search)

        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param match_all: match all flag, if True return only packages matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags
        '''
        # FIXME: Add support for search in pkgtags, when supported in dnf
        showdups = not newest_only
        result = self.base.search(fields, keys, match_all, showdups)
        pkg_ids = self._to_package_id_list(result)
        return pkg_ids

    def _search_with_attr(self, fields, keys, attrs, match_all, newest_only, tags):
        '''
        Search for for packages, where given fields contain given key words
        (Helper for Search)

        :param fields: list of fields to search in
        :param keys: list of keywords to search for
        :param attrs: list of extra attributes to get
        :param match_all: match all flag, if True return only packages matching all keys
        :param newest_only: return only the newest version of a package
        :param tags: seach pkgtags
        '''
        # FIXME: Add support for search in pkgtags, when supported in dnf
        showdups = not newest_only
        pkgs = self.base.search(fields, keys, match_all, showdups)
        values = [self._get_po_list(po,attrs) for po in pkgs]
        return values

    def _expire_cache(self):
        try:
            self.base.expire_cache()
            self.base.reset(sack=True)
            self.base.setup_base()
            return True
        except dnf.exceptions.RepoError as e:
            self.logger.error(str(e))
            self.ErrorMessage(str(e))
            return False

    def _get_packages_by_name(self, name, newest_only):
        '''
        Get a list of pkg ids from a name pattern
        (Helper for GetPackagesByName)

        :param name: name pattern
        :param newest_only: True = get newest packages only
        '''
        qa = self._get_po_by_name(name, newest_only)
        pkg_ids = self._to_package_id_list(qa)
        return pkg_ids

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
        return list(pkgs)

    def _get_groups(self):
        '''
        make a list with categoties and there groups
        This is the old way of yum groups, where a group is a collection of mandatory, default and optional pacakges
        and the group is installed when all mandatory & default packages is installed.
        '''
        all_groups = []
        if not self.base.comps: # lazy load the comps metadata
            self.base.read_comps()
        cats = self.base.comps.categories
        for category in cats:
            cat = (category.name, category.ui_name, category.ui_description)
            cat_grps = []
            for obj in category.group_ids:
                grp = self.base.comps.group_by_pattern(obj.name) # get the dnf group obj
                if grp:
                    elem = (grp.id, grp.ui_name, grp.ui_description, grp.installed)
                    cat_grps.append(elem)
            cat_grps.sort()
            all_groups.append((cat, cat_grps))
        all_groups.sort()
        return json.dumps(all_groups)

    def _get_repositories(self, filter):
        '''
        Get the value a list of repo ids
        :param filter: filter to limit the listed repositories
        '''
        if filter == '' or filter == 'enabled':
            repos = [repo.id for repo in self.base.repos.iter_enabled()]
        else:
            repos = [repo.id for repo in  self.base.repos.get_matching(filter)]
        return repos


    def _get_config(self, setting):
        '''
        Get the value of a yum config setting
        it will return a JSON string of the config
        :param setting: name of setting (debuglevel etc..)
        '''
        if setting == '*': # Return all config
            cfg = self.base.conf
            all_conf = dict([(c,getattr(cfg,c)) for c in cfg.iterkeys()])
            value =  json.dumps(all_conf)
        elif hasattr(self.base.conf, setting):
            value = json.dumps(getattr(self.base.conf, setting))
        else:
            value = json.dumps(None)
        return value
        return value

    def _get_repo(self, repo_id ):
        '''
        Get information about a give repo_id
        the repo setting will be returned as dictionary in JSON format
        :param repo_id:
        '''
        value = json.dumps(None)
        repo = self.base.repos.get(repo_id, None) # get the repo object
        if repo:
            repo_conf = dict([(c,getattr(repo,c)) for c in repo.iterkeys()])
            value = json.dumps(repo_conf)
        return value

    def _set_enabled_repos(self, repo_ids):
        '''
        Enable a list of repos, disable the ones not in list
        '''
        self._reset_base()
        self._get_base(reset=True, load_sack=False)
        for repo in self.base.repos.all():
            if repo.id in repo_ids:
                logger.debug("  enabled : %s ",repo.id)
                repo.enable()
            else:
                repo.disable()
        self._base.setup_base() # load the sack with the current enabled repos


    def _get_packages(self, pkg_filter):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        '''
        if pkg_filter in ['installed','available','updates','obsoletes','recent','extras']:
            pkgs = getattr(self.base.packages,pkg_filter)
            value = self._to_package_id_list(pkgs)
        else:
            value = []
        return value

    def _get_package_with_attributes(self, pkg_filter, fields):
        '''
        Get a list of package ids, based on a package pkg_filterer
        :param pkg_filter: pkg pkg_filter string ('installed','updates' etc)
        '''
        value = []
        if pkg_filter in ['installed','available','updates','obsoletes','recent','extras']:
            pkgs = getattr(self.base.packages,pkg_filter)
            value = [self._get_po_list(po,fields) for po in pkgs]
        return value

    def _get_attribute(self, id, attr):
        '''
        Get an attribute from a yum package id
        it will return a python repr string of the attribute
        :param id: yum package id
        :param attr: name of attribute (summary, size, description, changelog etc..)
        '''
        po = self._get_po(id)
        if po:
            if attr in FAKE_ATTR: # is this a fake attr:
                value = json.dumps(self._get_fake_attributes(po, attr))
            elif hasattr(po, attr):
                value = json.dumps(getattr(po,attr))
            else:
                value = json.dumps(None)
        else:
            value = json.dumps(None)
        return value

    def _get_installed_na(self,name,arch):
        q = self.base.sack.query()
        inst = q.installed().filter(name=name, arch=arch).run()
        if inst:
            return inst[0]
        else:
            return None


    def _get_updateInfo(self, id):
        '''
        Get an Update Infomation e from a yum package id
        it will return a python repr string of the attribute
        :param id: yum package id
        '''
        po = self._get_po(id)
        if po:
            # TODO : updateinfo is not supported in DNF yet
            # https://bugzilla.redhat.com/show_bug.cgi?id=850912
            value = json.dumps(None)
        else:
            value = json.dumps(None)
        return value

    def _get_packages_by_name_with_attr(self,name, newest_only, attrs):
        """
        get packages matching a name wildcard with extra attributes
        """
        pkgs = self._get_po_by_name(name, newest_only)
        values = [self._get_po_list(po,attrs) for po in pkgs]
        return values

    def _get_group_pkgs(self, grp_id, grp_flt, fields):
        '''
        Get packages for a given grp_id and group filter
        '''
        pkgs = []
        grp = self.base.comps.group_by_pattern(grp_id)
        if grp:
            if grp_flt == 'all':
                pkg_names = []
                pkg_names.extend([p.name for p in grp.mandatory_packages ])# FIXME: mandatory_packages is not public API
                pkg_names.extend([p.name for p in grp.default_packages ]) # FIXME: default_packages is not public API
                pkg_names.extend([p.name for p in grp.optional_packages ])# FIXME: optional_packages is not public API
                best_pkgs = []
                for name in pkg_names:
                    best_pkgs.extend(self._get_po_by_name(name,True))
            else:
                pkg_names = []
                pkg_names.extend([p.name for p in grp.mandatory_packages ]) # FIXME: mandatory_packages is not public API
                pkg_names.extend([p.name for p in grp.default_packages ]) # FIXME: default_packages is not public API
                best_pkgs = []
                for name in pkg_names:
                    best_pkgs.extend(self._get_po_by_name(name,True))
            pkgs = self.base.packages.filter_packages(best_pkgs)
        else:
            pass
        value = [self._get_po_list(po,fields) for po in pkgs]
        return value

#===============================================================================
# Helper methods
#===============================================================================

    def _get_po_list(self, po, attrs):
        po_list = [self._get_id(po)]
        for attr in attrs:
            if attr in FAKE_ATTR: # is this a fake attr:
                value = self._get_fake_attributes(po, attr)
            elif hasattr(po, attr):
                value = getattr(po,attr)
            else:
                value = None
            po_list.append(value)
        return po_list

    def _get_id_time_list(self, hist_trans):
        '''
        return a list of (tid, isodate) pairs from a list of yum history transactions
        '''
        result = []
        for ht in hist_trans:
            tm = datetime.fromtimestamp(ht.end_timestamp)
            result.append((ht.tid, tm.isoformat()))
        return result

    def _get_fake_attributes(self,po, attr):
        '''
        Get Fake Attributes, a whey to useful stuff for a package there is not real
        attritbutes to the yum package object.
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

    def _get_downgrades(self,pkg):
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

    def _get_po(self,id):
        ''' find the real package from an package id'''
        n, e, v, r, a, repo_id = id.split(',')
        q = self.base.sack.query()
        if repo_id.startswith('@'): # installed package
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

    def _get_id(self,pkg):
        '''
        convert a yum package obejct to an id string containing (n,e,v,r,a,repo)
        :param pkg:
        '''
        values = [pkg.name, str(pkg.epoch), pkg.version, pkg.release, pkg.arch, pkg.ui_from_repo]
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

    def _get_base(self, reset = False, load_sack=True):
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
        if self._watchdog_disabled or self._is_working: # is working
            return True
        if not self._lock: # is locked
            if self._watchdog_count > self._timeout_idle:
                terminate = True
        else:
            if self._watchdog_count > self._timeout_locked:
                terminate = True
        if terminate: # shall we quit
            if self._can_quit:
                self._reset_base()
                Gtk.main_quit()
        else:
            self._watchdog_count += 1
            self.logger.debug("Watchdog : %i" % self._watchdog_count )
            return True

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
        pkgs = []
        for pkg in pkg_list:
            key = (pkg.name, pkg.arch)
            inst_pkg = self._inst_na.get(key, [None])[0]
            if inst_pkg and inst_pkg.evr == pkg.evr:
                if replace:
                    pkgs.append(inst_pkg)
            else:
                pkgs.append(pkg)
        return pkgs


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
    def all(self,showdups = False):
        '''
        all packages in the repositories
        installed ones are replace with the install package objects
        '''
        if showdups:
            return self.filter_packages(self.query.available().run())
        else:
            return self.filter_packages(self.query.latest().run())

    @property
    def available(self, showdups = False):
        '''
        available packages there is not installed yet
        '''
        if showdups:
            return self.filter_packages(self.query.available().run(), replace=False)
        else:
            return self.filter_packages(self.query.available().latest().run(), replace=False)

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
        recentlimit = now-(self._base.conf.recent*86400)
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
        dnf.Base.__init__(self)
        # FIXME: goal_parameters.allow_uninstall is not public api
        # make remove able to remove deps also
        self.goal_parameters.allow_uninstall = True
        self.parent = parent
        self.md_progress = MDProgress(parent)
        self.setup_cache()
        self.read_all_repos()
        self.progress = Progress(parent, max_err = 100)
        self.repos.all().set_progress_bar( self.md_progress)
        self._packages = None

    def expire_cache(self):
        self.cleanExpireCache() # FIXME : cleanExpireCache() is not public API

    def setup_base(self):
        self.fill_sack()
        self._packages = Packages(self)

    @property
    def packages(self):
        return self._packages

    def setup_cache(self):
        # perform the CLI-specific cachedir tricks
        conf = self.conf
        conf.releasever = None # This will take the current release
        # FIXME: This is not public API, but we want the same cache as dnf cli
        suffix = dnf.yum.parser.varReplace(dnf.const.CACHEDIR_SUFFIX, conf.yumvar)
        cli_cache = dnf.conf.CliCache(conf.cachedir, suffix)
        conf.cachedir = cli_cache.cachedir
        self._system_cachedir = cli_cache.system_cachedir
        logger.debug("dnf cachedir: %s" % conf.cachedir)

    def set_max_error(self, max_err):
        """
        Setup a new progress object with a new max number of download errors
        """
        self.progress = Progress(self.parent, max_err = max_err)

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
                pkgs = set(self.contains(attr,key).run())
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
            result = self.sack.query().filter(pkg=result).latest()
        return result

    def contains(self, attr, needle, ignore_case=True):
        fdict = {'%s__substr' % attr : needle}
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

    def end(self,payload, status, msg):
        name  = str(payload)
        if status == dnf.callback.STATUS_OK:
            self.parent.repoMetaDataProgress(name, 1.0)

    def progress(self, payload, done):
        name  = str(payload)
        cur_total_bytes = payload.download_size
        if cur_total_bytes:
            frac = done/float(cur_total_bytes)
        else:
            frac = 0.0
        if frac > self._last+0.01:
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


    def end(self,payload, status, msg):
        if status in [dnf.callback.STATUS_OK, dnf.callback.STATUS_ALREADY_EXISTS] : # payload download complete
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
            self.parent.downloadProgress(pload, frac, total_frac, self.download_files)

    def get_total(self):
        """ Get the total downloaded percentage"""
        tot = 0.0
        for value in self.dnl.values():
            tot += value
        frac = tot / self.total_size
        return frac

    def update(self):
        """ Output the current progress"""

        sys.stdout.write("Progress : %-3d %% (%d/%d)\r" % (self.last_pct,self.download_files, self.total_files))


def doTextLoggerSetup(logroot='dnfdaemon', logfmt='%(asctime)s: %(message)s', loglvl=logging.INFO):
    ''' Setup Python logging  '''
    logger = logging.getLogger(logroot)
    logger.setLevel(loglvl)
    formatter = logging.Formatter(logfmt, "%H:%M:%S")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.propagate = False
    logger.addHandler(handler)


