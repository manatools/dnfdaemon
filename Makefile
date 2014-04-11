PKGNAME = dnfdaemon
DATADIR=/usr/share
SYSCONFDIR=/etc
PKGDIR = $(DATADIR)/$(PKGNAME)
ORG_NAME = org.baseurl.DnfSystem
ORG_RO_NAME = org.baseurl.DnfSession
SUBDIRS = client/dnfdaemon
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)

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
	yum install perl-TimeDate gettext intltool rpmdevtools python-devel python3-devel python-sphinx python3-nose tito
	
# needs perl-TimeDate for git2cl
changelog:
	@git log --pretty --numstat --summary --after=2008-10-22 | tools/git2cl > ChangeLog
	
	
release:
	$(MAKE) changelog
	@tito tag 
	@git push
	@git push --tags origin
	@tito build -rpm

test-release:
	@sudo rm -rf /var/tito
	tito build --rpm --test
	
test-repo-build:
	@cd test/pkgs/ && ./build-rpms.sh
	@# Dnf cant clean a local repo
	@sudo rm -rf /var/cache/dnf/*/20/dnf-daemon-test
	@sudo rm -f /var/cache/dnf/*/20/dnf-daemon-test*

test-inst:
	$(MAKE) test-release
	@sudo dnf install /tmp/tito/noarch/*.rpm
	
rpms:
	tito build --rpm 
	

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
	@-sudo killall -9 -r "dnfdaemon-system" &> /dev/null 
	@-sudo killall -9 -r "dnfdaemon-session" &> /dev/null 
	

start-system:
	sudo dnfdaemon/dnfdaemon-system.py -d -v --notimeout

monitor-session:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSession',interface='org.baseurl.DnfSession'"	

monitor-system:
	dbus-monitor "type='signal',sender='org.baseurl.DnfSystem',interface='org.baseurl.DnfSystem'"	

FORCE:
	
