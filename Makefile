PKGNAME = dnfdaemon
APPNAME = $(PKGNAME)
DATADIR=/usr/share
SYSCONFDIR=/etc
PKGDIR = $(DATADIR)/$(PKGNAME)
ORG_NAME = org.baseurl.DnfSystem
ORG_RO_NAME = org.baseurl.DnfSession
SUBDIRS = python
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
TESTLIBS=python/:test/
PYVER3 := $(shell python3 -c 'import sys; print("%.3s" %(sys.version))')
GITDATE=git$(shell date +%Y%m%d)
VER_REGEX=\(^Version:\s*[0-9]*\.[0-9]*\.\)\(.*\)
BUMPED_MINOR=${shell VN=`cat ${APPNAME}.spec | grep Version| sed  's/${VER_REGEX}/\2/'`; echo $$(($$VN + 1))}
NEW_VER=${shell cat ${APPNAME}.spec | grep Version| sed  's/\(^Version:\s*\)\([0-9]*\.[0-9]*\.\)\(.*\)/\2${BUMPED_MINOR}/'}
NEW_REL=0.1.${GITDATE}
DIST=${shell rpm --eval "%{dist}"}
GIT_MASTER=master
CURDIR = ${shell pwd}
BUILDDIR= $(CURDIR)/build


all: subdirs
	
subdirs:
	for d in $(SUBDIRS); do make -C $$d; [ $$? = 0 ] || exit 1 ; done

clean:
	@rm -fv *~ *.tar.gz *.list *.lang 
	for d in $(SUBDIRS); do make -C $$d clean ; done

install:
	mkdir -p $(DESTDIR)$(DATADIR)/dbus-1/system-services
	mkdir -p $(DESTDIR)$(DATADIR)/dbus-1/services
	mkdir -p $(DESTDIR)$(SYSCONFDIR)/dbus-1/system.d
	mkdir -p $(DESTDIR)$(DATADIR)/polkit-1/actions
	mkdir -p $(DESTDIR)$(PKGDIR)
	install -m644 dbus/$(ORG_NAME).service $(DESTDIR)$(DATADIR)/dbus-1/system-services/.				
	install -m644 dbus/$(ORG_RO_NAME).service $(DESTDIR)$(DATADIR)/dbus-1/services/.				
	install -m644 dbus/$(ORG_NAME).conf $(DESTDIR)$(SYSCONFDIR)/dbus-1/system.d/.				
	install -m644 policykit1/$(ORG_NAME).policy $(DESTDIR)$(DATADIR)/polkit-1/actions/.				
	install -m755 daemon/dnfdaemon-system.py $(DESTDIR)/$(PKGDIR)/dnfdaemon-system
	install -m755 daemon/dnfdaemon-session.py $(DESTDIR)/$(PKGDIR)/dnfdaemon-session
	for d in $(SUBDIRS); do make DESTDIR=$(DESTDIR) -C $$d install; [ $$? = 0 ] || exit 1; done

uninstall:
	rm -f $(DESTDIR)$(DATADIR)/dbus-1/system-services/$(ORG_NAME).*
	rm -f $(DESTDIR)$(DATADIR)/dbus-1/services/$(ORG_RO_NAME).*
	rm -f $(DESTDIR)$(SYSCONFDIR)/dbus-1/system.d/$(ORG_NAME).*				
	rm -r $(DESTDIR)$(DATADIR)/polkit-1/actions/$(ORG_NAME).*		
	rm -rf $(DESTDIR)/$(PKGDIR)/

selinux:
	@$(MAKE) install
	semanage fcontext -a -t rpm_exec_t $(DESTDIR)/$(PKGDIR)/dnfdaemon-system
	restorecon $(DESTDIR)/$(PKGDIR_DNF)/dnfdaemon-system
	

# Run as root or you will get a password prompt 
run-tests-system: FORCE
	@sudo PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v test/test-system-*.py

# Run as root or you will get a password prompt 
run-tests-system-verbose: FORCE
	@sudo PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v -s test/test-system-*.py

# Run as root or you will get a password prompt 
run-tests-system-rw: FORCE
	@sudo PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v test/test-system-rw.py

run-tests-system-ro: FORCE
	@sudo PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v test/test-system-ro.py

run-tests-session: FORCE
	@PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v test/test-session-api.py

run-tests-session-verbose: FORCE
	@PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v -s test/test-session-api.py

run-tests-devel: FORCE
	@PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v -s test/unit-devel.py

run-tests-unit: FORCE
	@PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v -s test/test_common.py

instdeps:
	sudo dnf install python-nose python3-gobject pygobject3	python3-nose

get-builddeps:
	sudo dnf install perl-TimeDate gettext intltool rpmdevtools python-devel python3-devel python-sphinx python3-nose tito
	

build-setup:
	@rm -rf build/  &>/dev/null ||:
	@mkdir -p build/SOURCES ||:
	@mkdir -p build/SRPMS ||:
	@mkdir -p build/RPMS ||:
	@mkdir -p build/BUILD ||:
	@mkdir -p build/BUILDROOT ||:
	
test-repo-build:
	@cd test/pkgs/ && ./build-rpms.sh
	@# Dnf cant clean a local repo
	@sudo rm -rf /var/cache/dnf/*/20/dnf-daemon-test
	@sudo rm -f /var/cache/dnf/*/20/dnf-daemon-test*

test-inst:
	$(MAKE) test-release
	@sudo dnf install --setopt=installonly_limit=0  build/RPMS/noarch/*$(PKGNAME)*.rpm

test-reinst:
	$(MAKE) test-release
	@sudo dnf reinstall --setopt=installonly_limit=0 build/RPMS/noarch/*$(PKGNAME)*.rpm
	
test-upd:
	$(MAKE) test-release
	@sudo dnf update --setopt=installonly_limit=0 build/RPMS/noarch/*$(PKGNAME)*.rpm

rpms:
	$(MAKE) build-setup
	$(MAKE) archive
	@rpmbuild --define '_topdir $(BUILDDIR)' -ba $(PKGNAME).spec
	
archive:
	git archive --prefix=$(PKGNAME)-$(VERSION)/ HEAD | xz > build/SOURCES/$(PKGNAME)-$(VERSION).tar.xz
	@echo "The archive is in build/SOURCES/$(PKGNAME)-$(VERSION).tar.xz"
	
	
# needs perl-TimeDate for git2cl
changelog:
	@git log --pretty --numstat --summary | tools/git2cl > ChangeLog
	

release:
	@git commit -a -m "bumped version to $(VERSION)"
	@$(MAKE) changelog
	@git commit -a -m "updated ChangeLog"
	@git push
	@git tag -f -m "Added ${APPNAME}-${VERSION} release tag" ${APPNAME}-${VERSION}
	@git push --tags origin
	@$(MAKE) rpms

test-cleanup:	
	@rm -rf ${APPNAME}-${VERSION}.test.tar.gz
	@echo "Cleanup the git release-test local branch"
	@git checkout -f
	@git checkout ${GIT_MASTER}
	@git branch -D release-test

show-vars:
	@echo ${GITDATE}
	@echo ${BUMPED_MINOR}
	@echo ${NEW_VER}-${NEW_REL}
	
test-release:
	$(MAKE) build-setup
	@git checkout -b release-test
	# +1 Minor version and add 0.1-gitYYYYMMDD release
	@cat ${APPNAME}.spec | sed  -e 's/${VER_REGEX}/\1${BUMPED_MINOR}/' -e 's/\(^Release:\s*\)\([0-9]*\)\(.*\)./\10.1.${GITDATE}%{?dist}/' > ${APPNAME}-test.spec ; mv ${APPNAME}-test.spec ${APPNAME}.spec
	@git commit -a -m "bumped ${APPNAME} version ${NEW_VER}-${NEW_REL}"
	# Make Changelog
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	@git commit -a -m "updated ChangeLog"
	# Make archive
	@rm -rf ${APPNAME}-${NEW_VER}.tar.gz
	@git archive --format=tar --prefix=$(PKGNAME)-$(NEW_VER)/ HEAD | xz >build/SOURCES/${PKGNAME}-$(NEW_VER).tar.xz
	# Build RPMS 
	@-rpmbuild --define '_topdir $(BUILDDIR)' -ba ${PKGNAME}.spec
	@$(MAKE) test-cleanup
	

exit-session:
	@/usr/bin/dbus-send --session --print-reply --dest="org.baseurl.DnfSession" / org.baseurl.DnfSession.Exit

exit-system:
	@sudo /usr/bin/dbus-send --system --print-reply --dest="org.baseurl.DnfSystem" / org.baseurl.DnfSystem.Exit
	
exit-both:
	@/usr/bin/dbus-send --session --print-reply --dest="org.baseurl.DnfSession" / org.baseurl.DnfSession.Exit
	@sudo /usr/bin/dbus-send --system --print-reply --dest="org.baseurl.DnfSystem" / org.baseurl.DnfSystem.Exit
	
start-session:
	PYTHONPATH=python/ daemon/dnfdaemon-session.py -d -v --notimeout

kill-both:
	@-sudo killall -9 -r "dnfdaemon-system\.py" &> /dev/null 
	@-sudo killall -9 -r "dnfdaemon-session\.py" &> /dev/null 
	@-sudo killall -9 -r "dnfdaemon-system" &> /dev/null 
	@-sudo killall -9 -r "dnfdaemon-session" &> /dev/null 
		
	
start-system:
	@sudo PYTHONPATH=python/ daemon/dnfdaemon-system.py -d -v --notimeout

monitor-session:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSession',interface='org.baseurl.DnfSession'"	

monitor-system:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSystem',interface='org.baseurl.DnfSystem'"	

FORCE:
	
