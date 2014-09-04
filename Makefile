PKGNAME = dnfdaemon
DATADIR=/usr/share
SYSCONFDIR=/etc
PKGDIR = $(DATADIR)/$(PKGNAME)
ORG_NAME = org.baseurl.DnfSystem
ORG_RO_NAME = org.baseurl.DnfSession
SUBDIRS = python
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
TESTLIBS=python/:test/
PYVER3 := $(shell python3 -c 'import sys; print("%.3s" %(sys.version))')

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

run-tests-unit: FORCE
	@PYTHONPATH=$(TESTLIBS) nosetests-$(PYVER3) -v -s test/test_common.py

instdeps:
	sudo dnf install python-nose python3-gobject pygobject3	python3-nose

get-builddeps:
	sudo dnf install perl-TimeDate gettext intltool rpmdevtools python-devel python3-devel python-sphinx python3-nose tito
	
# needs perl-TimeDate for git2cl
changelog:
	@git log --pretty --numstat --summary --after=2008-10-22 | tools/git2cl > ChangeLog
	

build-setup:
	@rm -rf build/  &>/dev/null ||:
	@mkdir -p build ||:
	
release:
	$(MAKE) build-setup
	$(MAKE) changelog
	@git commit -a -m "updated ChangeLog"	
	@tito tag
	@git push
	@git push --tags origin
	@tito build --rpm  -o build/

test-release:
	$(MAKE) build-setup
	tito build --rpm --test -o build/
	
test-repo-build:
	@cd test/pkgs/ && ./build-rpms.sh
	@# Dnf cant clean a local repo
	@sudo rm -rf /var/cache/dnf/*/20/dnf-daemon-test
	@sudo rm -f /var/cache/dnf/*/20/dnf-daemon-test*

test-inst:
	$(MAKE) test-release
	@sudo dnf install build/noarch/*.rpm
	
rpms:
	tito build --rpm -o build/
	

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
	
