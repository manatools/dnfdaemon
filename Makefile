PKGNAME = dnfdaemon
DATADIR=/usr/share
SYSCONFDIR=/etc
PKGDIR = $(DATADIR)/$(PKGNAME)
ORG_NAME = org.baseurl.DnfSystem
ORG_RO_NAME = org.baseurl.DnfSession
SUBDIRS = client/dnfdaemon
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
PYTHON=python
GITDATE=git$(shell date +%Y%m%d)
VER_REGEX=\(^Version:\s*[0-9]*\.[0-9]*\.\)\(.*\)
BUMPED_MINOR=${shell VN=`cat ${PKGNAME}.spec | grep Version| sed  's/${VER_REGEX}/\2/'`; echo $$(($$VN + 1))}
NEW_VER=${shell cat ${PKGNAME}.spec | grep Version| sed  's/\(^Version:\s*\)\([0-9]*\.[0-9]*\.\)\(.*\)/\2${BUMPED_MINOR}/'}
NEW_REL=0.1.${GITDATE}
DIST=${shell rpm --eval "%{dist}"}

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
	install -m755 dnfdaemon/dnfdaemon-system.py $(DESTDIR)/$(PKGDIR)/dnfdaemon-system
	install -m755 dnfdaemon/dnfdaemon-session.py $(DESTDIR)/$(PKGDIR)/dnfdaemon-session
	install -m644 dnfdaemon/common.py $(DESTDIR)/$(PKGDIR)/.
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
test-verbose: FORCE
	@sudo nosetests-3.3 -v -s test/


# Run as root or you will get a password prompt
test: FORCE
	@sudo nosetests-3.3 -v test/

# Run as root or you will get a password prompt 
test-system: FORCE
	@sudo nosetests-3.3 -v test/test-system-api.py

# Run as root or you will get a password prompt 
test-system-verbose: FORCE
	@sudo nosetests-3.3 -v -s test/test-system-api.py

test-session: FORCE
	@nosetests-3.3 -v test/test-session-api.py

test-session-verbose: FORCE
	@nosetests-3.3 -v -s test/test-session-api.py

# Run as root or you will get a password prompt for each test method :)
test-devel: FORCE
	@nosetests-3.3 -v -s test/unit-devel.py

instdeps:
	sudo yum install python-nose python3-gobject pygobject3	python3-nose

get-builddeps:
	yum install perl-TimeDate gettext intltool rpmdevtools python-devel python3-devel python-sphinx python3-nose

archive:
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	@git archive --format=tar --prefix=$(PKGNAME)-$(VERSION)/ HEAD | gzip -9v >${PKGNAME}-$(VERSION).tar.gz
	@cp ${PKGNAME}-$(VERSION).tar.gz $(shell rpm -E '%_sourcedir')
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	@echo "The archive is in ${PKGNAME}-$(VERSION).tar.gz"
	
# needs perl-TimeDate for git2cl
changelog:
	@git log --pretty --numstat --summary --after=2008-10-22 | tools/git2cl > ChangeLog
	
upload: FORCE
	@scp ~/rpmbuild/SOURCES/${PKGNAME}-${VERSION}.tar.gz fedorahosted.org:yumex
	
release:
	@git commit -a -m "bumped version to $(VERSION)"
	@git push
	@git tag -f -m "Added ${PKGNAME}-${VERSION} release tag" ${PKGNAME}-${VERSION}
	@git push --tags origin
	@$(MAKE) archive
	@$(MAKE) upload

test-cleanup:	
	@rm -rf ${PKGNAME}-${VERSION}.test.tar.gz
	@echo "Cleanup the git release-test local branch"
	@git checkout -f
	@git checkout master
	@git branch -D release-test

show-vars:
	@echo ${GITDATE}
	@echo ${BUMPED_MINOR}
	@echo ${NEW_VER}-${NEW_REL}
	
test-release:
	@git checkout -b release-test
	# +1 Minors version and add 0.1-gitYYYYMMDD release
	@cat ${PKGNAME}.spec | sed  -e 's/${VER_REGEX}/\1${BUMPED_MINOR}/' -e 's/\(^Release:\s*\)\([0-9]*\)\(.*\)./\10.1.${GITDATE}%{?dist}/' > ${PKGNAME}-test.spec ; mv ${PKGNAME}-test.spec ${PKGNAME}.spec
	@git commit -a -m "bumped ${PKGNAME} version ${NEW_VER}-${NEW_REL}"
	# Make Changelog
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	@git commit -a -m "updated ChangeLog"
	# Make archive
	@rm -rf ${PKGNAME}-${NEW_VER}.tar.gz
	@git archive --format=tar --prefix=$(PKGNAME)-$(NEW_VER)/ HEAD | gzip -9v >${PKGNAME}-$(NEW_VER).tar.gz
	@cp ${PKGNAME}-$(NEW_VER).tar.gz $(shell rpm -E '%_sourcedir')
	@rm -rf ${PKGNAME}-$(NEW_VER).tar.gz
	# Build RPMS
	@rpmbuild -ba ${PKGNAME}.spec
	@$(MAKE) test-cleanup

test-inst:
	@$(MAKE) test-release
	sudo yum install ~/rpmbuild/RPMS/noarch/*${PKGNAME}-${NEW_VER}*.rpm

test-reinst:
	@$(MAKE) test-release
	sudo yum reinstall ~/rpmbuild/RPMS/noarch/*${PKGNAME}-${NEW_VER}*.rpm
	
rpm:
	@$(MAKE) archive
	@rpmbuild -ba ${PKGNAME}.spec
	
test-builds:
	@$(MAKE) test-release
	@ssh timlau.fedorapeople.org rm -f public_html/files/${PKGNAME}/*
	@scp ${PKGNAME}-${NEW_VER}.tar.gz timlau.fedorapeople.org:public_html/files/${PKGNAME}/${PKGNAME}-${NEW_VER}-${GITDATE}.tar.gz
	@scp ~/rpmbuild/RPMS/noarch/${PKGNAME}-${NEW_VER}*.rpm timlau.fedorapeople.org:public_html/files/${PKGNAME}/.
	@scp ~/rpmbuild/RPMS/noarch/python-${PKGNAME}-${NEW_VER}*.rpm timlau.fedorapeople.org:public_html/files/${PKGNAME}/.
	@scp ~/rpmbuild/RPMS/noarch/python3-${PKGNAME}-${NEW_VER}*.rpm timlau.fedorapeople.org:public_html/files/${PKGNAME}/.
	@scp ~/rpmbuild/SRPMS/${PKGNAME}-${NEW_VER}*.rpm timlau.fedorapeople.org:public_html/files/${PKGNAME}/.
	
review:	
	@ssh timlau.fedorapeople.org rm -f public_html/files/${PKGNAME}/*
	@scp ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}*.src.rpm  timlau.fedorapeople.org:public_html/files/${PKGNAME}/.
	@scp ${PKGNAME}.spec timlau.fedorapeople.org:public_html/files/${PKGNAME}/.


exit-session:
	@/usr/bin/dbus-send --session --print-reply --dest="org.baseurl.DnfSession" / org.baseurl.DnfSession.Exit

exit-system:
	@sudo /usr/bin/dbus-send --system --print-reply --dest="org.baseurl.DnfSystem" / org.baseurl.DnfSystem.Exit
	
exit-both:
	@/usr/bin/dbus-send --session --print-reply --dest="org.baseurl.DnfSession" / org.baseurl.DnfSession.Exit
	@sudo /usr/bin/dbus-send --system --print-reply --dest="org.baseurl.DnfSystem" / org.baseurl.DnfSystem.Exit
	
start-session:
	dnfdaemon/dnfdaemon-session.py -d -v --notimeout

kill-both:
	@-sudo killall -9 -r "dnfdaemon-system\.py" &> /dev/null 
	@-sudo killall -9 -r "dnfdaemon-session\.py" &> /dev/null 
	

start-system:
	sudo dnfdaemon/dnfdaemon-system.py -d -v --notimeout

monitor-session:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSession',interface='org.baseurl.DnfSession'"	

monitor-system:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSystem',interface='org.baseurl.DnfSystem'"	

FORCE:
	
