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
dnf base and callbacks for dnfdaemon dbus services
"""
from time import time

import dnf
import dnf.const
import dnf.conf
import dnf.exceptions
import dnf.callback
import dnf.comps
import dnf.rpm
import dnf.subject
import dnf.transaction
import dnf.yum
import hawkey
import logging
import sys

logger = logging.getLogger('dnfdaemon.base.dnf')


class DnfBase(dnf.Base):
    """An extended version of the dnf.Base class."""

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
        """Make the current cache expire"""
        self.cleanExpireCache()  # FIXME : cleanExpireCache() is not public API

    def setup_base(self):
        """Setup dnf Sack and init packages helper"""
        self.fill_sack()
        self._packages = Packages(self)

    @property
    def packages(self):
        return self._packages

    def setup_cache(self):
        """Setup the dnf cache, same as dnf cli"""
        # FIXME: This is not public API, but we want the same cache as dnf cli
        conf = self.conf
        releasever = dnf.rpm.detect_releasever('/')
        conf.releasever = releasever
        subst = conf.substitutions
        suffix = dnf.yum.parser.varReplace(dnf.const.CACHEDIR_SUFFIX, subst)
        cli_cache = dnf.conf.CliCache(conf.cachedir, suffix)
        conf.cachedir = cli_cache.cachedir
        self._system_cachedir = cli_cache.system_cachedir
        logger.debug("cachedir: %s", conf.cachedir)

    def set_max_error(self, max_err):
        """Setup a new progress object with a new
        max number of download errors.
        """
        self.progress = Progress(self.parent, max_err=max_err)

    def search(self, fields, values, match_all=True, showdups=False):
        """Search in a list of package attributes for a list of keys.

        :param fields: package attributes to search in
        :param values: the values to match
        :param match_all: match all values (default)
        :param showdups: show duplicate packages or latest (default)
        :return: a list of package objects
        """
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


class Packages:
    """This class gives easier access to getting packages from the dnf Sack."""

    def __init__(self, base):
        self._base = base
        self._sack = base.sack
        self._inst_na = self._sack.query().installed().na_dict()

    def filter_packages(self, pkg_list, replace=True):
        """Filter a list of package objects and replace
        the installed ones with the installed object, instead
        of the available object.
        """
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
        """Get the query from the current sack"""
        return self._sack.query()

    @property
    def installed(self):
        """Get installed packages."""
        return self.query.installed().run()

    @property
    def updates(self):
        """Get available updates."""
        return self.query.upgrades().latest().run()

    @property
    def all(self, showdups=False):
        """Get all packages installed and available.

        If a package is install, only the installed package object is
        returned
        """
        if showdups:
            return self.filter_packages(self.query.available().run())
        else:
            return self.filter_packages(self.query.latest().run())

    @property
    def available(self, showdups=False):
        """Get available packages."""
        if showdups:
            return self.filter_packages(self.query.available().run(),
                                        replace=False)
        else:
            return self.filter_packages(self.query.available().latest().run(),
                                        replace=False)

    @property
    def extras(self):
        """Get installed packages, not in current enabled repos."""
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
        """Get available obsoletes."""
        inst = self.query.installed()
        return self.query.filter(obsoletes=inst)

    @property
    def recent(self, showdups=False):
        """Get recent packages."""
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


class MDProgress(dnf.callback.DownloadProgress):
    """Metadata Download callback handler."""

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
    """Package Download callback handler"""

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
                raise dnf.exceptions.DownloadError(self._dnl_errors)
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
        """Get the total downloaded percentage."""
        tot = 0.0
        for value in self.dnl.values():
            tot += value
        frac = tot / self.total_size
        return frac

    def update(self):
        """Output the current progress."""

        sys.stdout.write("Progress : %-3d %% (%d/%d)\r" %
                         (self.last_pct,
                          self.download_files,
                          self.total_files))
