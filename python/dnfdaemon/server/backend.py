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
from dnf.i18n import _, ucd
from dnf.yum import misc

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
import itertools
import logging
import sys
import re
import os

logger = logging.getLogger('dnfdaemon.base.dnf')

UPDINFO_MAIN = ['id', 'title', 'type', 'description']


class DnfBase(dnf.Base):
    """An extended version of the dnf.Base class."""

    def __init__(self, parent):
        super(DnfBase, self).__init__()
        self.parent = parent
        self.md_progress = MDProgress(parent)

        try:
            self.init_plugins()
        except RuntimeError as err:
            logger.info("Failed to init plugins: %s", err)
        else:
            logger.debug("pre_configure plugins...")
            self.pre_configure_plugins()
            logger.debug("configure plugins...")
            self.configure_plugins()

        RELEASEVER = dnf.rpm.detect_releasever(self.conf.installroot)
        self.conf.substitutions['releasever'] = RELEASEVER
        self.conf.read()  # read the dnf.conf
        self.read_all_repos()
        self.progress = Progress(parent)
        self.repos.all().set_progress_bar(self.md_progress)
        self._packages = None

    def _tree(self, dirpath):
      """Traverse dirpath recursively and yield relative filenames."""
      for root, dirs, files in os.walk(dirpath):
          base = os.path.relpath(root, dirpath)
          for f in files:
              path = os.path.join(base, f)
              yield os.path.normpath(path)

    def _filter(self, files, patterns):
      """Yield those filenames that match any of the patterns."""
      return (f for f in files for p in patterns if re.match(p, f))

    def _clean(self, dirpath, files):
      """Remove the given filenames from dirpath."""
      count = 0
      for f in files:
          path = os.path.join(dirpath, f)
          logger.debug(_('Removing file %s'), path)
          misc.unlink_f(path)
          count += 1
      return count

    def _removeCacheFiles(self):
      ''' Remove solv and xml files '''
      cachedir =  self.conf.cachedir

      types = [ 'metadata', 'packages',  'dbcache' ]
      files = list(self._tree(cachedir))
      logger.debug(_('Cleaning data: ' + ' '.join(types)))

      patterns = [dnf.repo.CACHE_FILES[t] for t in types]
      count = self._clean(cachedir, self. _filter(files, patterns))
      logger.info( '%d file removed', count)

    def expire_cache(self):
        """Make the current cache expire"""
        for repo in self.repos.iter_enabled():
            # see https://bugzilla.redhat.com/show_bug.cgi?id=1629378
            try:
                # works up to dnf 3.4 (3.4 took it away)
                repo._md_expire_cache()
                logger.debug('md expire cache')
            except AttributeError:
                # works from libdnf 0.18.0 (I think)
                repo._repo.expire()
                logger.debug('repo expire (no md)')
        self._removeCacheFiles()

    def setup_base(self):
        """Setup dnf Sack and init packages helper"""
        logger.debug('setup DnfBase sack')
        self.fill_sack()
        logger.debug('setup packages')
        self._packages = Packages(self)

    @property
    def packages(self):
        return self._packages

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

###############################################################################
# code copied from dnf for non public API related
#
# FIXME: this is copied from dnf/base.py, because there is no public
#        API to handle gpg signatures.
###############################################################################
    def _sig_check_pkg(self, po):
        """Verify the GPG signature of the given package object.

        :param po: the package object to verify the signature of
        :return: (result, error_string)
           where result is::

              0 = GPG signature verifies ok or verification is not required.
              1 = GPG verification failed but installation of the right GPG key
                    might help.
              2 = Fatal GPG verification error, give up.
        """
        if po._from_cmdline:
            check = self.conf.localpkg_gpgcheck
            hasgpgkey = 0
        else:
            repo = self.repos[po.repoid]
            check = repo.gpgcheck
            hasgpgkey = not not repo.gpgkey

        if check:
            root = self.conf.installroot
            ts = dnf.rpm.transaction.initReadOnlyTransaction(root)
            sigresult = dnf.rpm.miscutils.checkSig(ts, po.localPkg())
            localfn = os.path.basename(po.localPkg())
            del ts
            if sigresult == 0:
                result = 0
                msg = ''

            elif sigresult == 1:
                if hasgpgkey:
                    result = 1
                else:
                    result = 2
                msg = _('Public key for %s is not installed') % localfn

            elif sigresult == 2:
                result = 2
                msg = _('Problem opening package %s') % localfn

            elif sigresult == 3:
                if hasgpgkey:
                    result = 1
                else:
                    result = 2
                result = 1
                msg = _('Public key for %s is not trusted') % localfn

            elif sigresult == 4:
                result = 2
                msg = _('Package %s is not signed') % localfn

        else:
            result = 0
            msg = ''

        return result, msg

    def _get_key_for_package(self, po, askcb=None, fullaskcb=None):
        """Retrieve a key for a package. If needed, use the given
        callback to prompt whether the key should be imported.

        :param po: the package object to retrieve the key of
        :param askcb: Callback function to use to ask permission to
           import a key.  The arguments *askck* should take are the
           package object, the userid of the key, and the keyid
        :param fullaskcb: Callback function to use to ask permission to
           import a key.  This differs from *askcb* in that it gets
           passed a dictionary so that we can expand the values passed.
        :raises: :class:`dnf.exceptions.Error` if there are errors
           retrieving the keys
        """
        repo = self.repos[po.repoid]
        keyurls = repo.gpgkey
        key_installed = False

        def _prov_key_data(msg):
            msg += _('Failing package is: %s') % (po) + '\n '
            msg += _('GPG Keys are configured as: %s') % \
                    (', '.join(repo.gpgkey) + '\n')
            return '\n\n\n' + msg

        user_cb_fail = False
        for keyurl in keyurls:
            keys = dnf.crypto.retrieve(keyurl, repo)

            for info in keys:
                ts = self._rpmconn.readonly_ts
                # Check if key is already installed
                if misc.keyInstalled(ts, info.rpm_id, info.timestamp) >= 0:
                    msg = _('GPG key at %s (0x%s) is already installed')
                    logger.info(msg, keyurl, info.short_id)
                    continue

                # Try installing/updating GPG key
                info.url = keyurl
                dnf.crypto.log_key_import(info)
                rc = False
                if self.conf.assumeno:
                    rc = False
                elif self.conf.assumeyes:
                    rc = True

                # grab the .sig/.asc for the keyurl, if it exists if it
                # does check the signature on the key if it is signed by
                # one of our ca-keys for this repo or the global one then
                # rc = True else ask as normal.

                elif fullaskcb:
                    rc = fullaskcb({"po": po, "userid": info.userid,
                                    "hexkeyid": info.short_id,
                                    "keyurl": keyurl,
                                    "fingerprint": info.fingerprint,
                                    "timestamp": info.timestamp})
                elif askcb:
                    rc = askcb(po, info.userid, info.short_id)

                if not rc:
                    user_cb_fail = True
                    continue

                # Import the key
                result = ts.pgpImportPubkey(misc.procgpgkey(info.raw_key))
                if result != 0:
                    msg = _('Key import failed (code %d)') % result
                    raise dnf.exceptions.Error(_prov_key_data(msg))
                logger.info(_('Key imported successfully'))
                key_installed = True

        if not key_installed and user_cb_fail:
            raise dnf.exceptions.Error(_("Didn't install any keys"))

        if not key_installed:
            msg = _('The GPG keys listed for the "%s" repository are '
                    'already installed but they are not correct for this '
                    'package.\n'
                    'Check that the correct key URLs are configured for '
                    'this repository.') % repo.name
            raise dnf.exceptions.Error(_prov_key_data(msg))

        # Check if the newly installed keys helped
        result, errmsg = self._sig_check_pkg(po)
        if result != 0:
            msg = _("Import of key(s) didn't help, wrong key(s)?")
            logger.info(msg)
            errmsg = ucd(errmsg)
            raise dnf.exceptions.Error(_prov_key_data(errmsg))


class Packages:
    """This class gives easier access to getting packages from the dnf Sack."""

    def __init__(self, base):
        self._base = base
        self._sack = base.sack
        self._inst_na = self._sack.query().installed()._na_dict()

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
        pkgs = []
        try:
            # we have to do upgrade_all & resolve
            # to make sure pkgs exclude by repo priority etc
            # get handled.
            self._base.upgrade_all()
            self._base.resolve(allow_erasing=True)
        except dnf.exceptions.DepsolveError as e:
            logger.debug(str(e))
            return pkgs
        # return install/upgrade type pkgs from transaction
        for tsi in self._base.transaction:
            #print(tsi.op_type, tsi.installed, tsi.erased, tsi.obsoleted)
            if tsi.action == dnf.transaction.PKG_UPGRADE:
                pkgs.append(tsi.pkg)
            elif tsi.action == dnf.transaction.PKG_INSTALL:
                # action is INSTALL, then it should be a installonlypkg
                pkgs.append(tsi.pkg)
        return pkgs

    @property
    def updates_all(self):
        return self.query.upgrades().latest().run()

    @property
    def all(self):
        """Get all packages installed and available.

        If a package is install, only the installed package object is
        returned
        """
        return self.get_all()

    def get_all(self, showdups=False):
        if showdups:
            return self.filter_packages(self.query.available().run())
        else:
            return self.filter_packages(self.query.latest().run())

    @property
    def available(self):
        """Get available packages."""
        return self.get_available()

    def get_available(self, showdups=False):
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

    def __init__(self, parent):
        super(Progress, self).__init__()
        self.parent = parent
        self.max_err = 1
        self.total_files = 0
        self.total_size = 0.0
        self.download_files = 0
        self.download_size = 0.0
        self._dnl_errors = {}
        self._err_count = 0
        self.dnl = {}
        self.last_frac = 0

    def start(self, total_files, total_size, total_drpms=0):
        self.total_files = total_files
        self.total_size = float(total_size)
        self.download_files = 0
        self.download_size = 0.0
        self.max_err = int(total_files / 2) + 1
        logger.debug('setting max_err to : %d', self.max_err)
        self.parent.downloadStart(total_files, total_size)

    def end(self, payload, status, msg):
        # payload download complete
        logger.debug('download status : {} - {}'.format(status, str(payload)))
        if status in [dnf.callback.STATUS_OK,
                      dnf.callback.STATUS_ALREADY_EXISTS,
                      dnf.callback.STATUS_DRPM]:
            self.download_files += 1
        elif status == dnf.callback.STATUS_FAILED:
            pload = str(payload)
            if pload in self._dnl_errors:
                self._dnl_errors[pload].append(msg)
                # if more than 10 error on a single payload,
                # increase total errors.
                if len(self._dnl_errors[pload]) > 10:
                    self._err_count += 1
                    logger.debug('dnl error # = %d', self._err_count)
            else:
                self._dnl_errors[pload] = [msg]
                self._err_count += 1  # count only once per file to dnl
                logger.debug('dnl error # = %d', self._err_count)
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


class UpdateInfo:
    """Wrapper class for dnf update advisories on a given po."""

    UPDINFO_MAIN = ['id', 'title', 'type', 'description']

    def __init__(self, po):
        self.po = po

    @staticmethod
    def advisories_iter(po):
        # FIXME: hawkey.package.get_advisories() is not public API
        return itertools.chain(po.get_advisories(hawkey.LT),
                               po.get_advisories(hawkey.GT | hawkey.EQ))

    def advisories_list(self):
        """list containing advisory information."""
        results = []
        for adv in self.advisories_iter(self.po):
            e = {}
            # main fields
            for field in UpdateInfo.UPDINFO_MAIN:
                e[field] = getattr(adv, field)
            dt = getattr(adv, 'updated')
            e['updated'] = dt.isoformat(' ')
            # TODO manage packages
            # references
            refs = []
            for ref in adv.references:
                ref_tuple = [ref.type, ref.id, ref.title, ref.url]
                refs.append(ref_tuple)
            e['references'] = refs
            results.append(e)
        return results
