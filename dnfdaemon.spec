%global dnf_org org.baseurl.Dnf
%global dnf_version 0.6.1

Name:           dnfdaemon
Version:        0.3.0
Release:        1%{?dist}
Summary:        DBus daemon for dnf package actions
License:        GPLv2+
URL:            https://github.com/timlau/dnf-daemon
Source0:        https://github.com/timlau/dnf-daemon/archive/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
Requires:       python3-dbus
Requires:       python3-dnf >= %{dnf_version}
Requires:       polkit
Requires:       python3-%{name} = %{version}-%{release}
Requires(post):     policycoreutils-python
Requires(postun):   policycoreutils-python

%description
Dbus daemon for performing package actions with the dnf package manager

%prep
%setup -q

%build
# Nothing to build

%install
make install DESTDIR=$RPM_BUILD_ROOT DATADIR=%{_datadir} SYSCONFDIR=%{_sysconfdir}

%package -n python3-%{name}
Summary:        %{name} python support libs
Group:          Applications/System
BuildRequires:  python3-devel
Requires:       python3-gobject

%description -n python3-%{name}
%{name} python support libs

%files -n  python3-%{name}
%{python3_sitelib}/%{name}/__*
%{python3_sitelib}/%{name}/server/*


%package -n python3-%{name}-client
Summary:        Python 3 api for communicating with the dnf-daemon DBus service
Group:          Applications/System
BuildRequires:  python3-devel
Requires:       %{name} = %{version}-%{release}
Requires:       python3-gobject

%description -n python3-%{name}-client
Python 3 api for communicating with the dnf-daemon DBus service

%files -n  python3-%{name}-client
%{python3_sitelib}/%{name}/client

%package -n python-%{name}-client
Summary:        Python 2 api for communicating with the dnf-daemon DBus service
Group:          Applications/System
BuildRequires:  python2-devel
Requires:       %{name} = %{version}-%{release}
Requires:       pygobject3

%description -n python-%{name}-client
Python 2 api for communicating with the dnf-daemon DBus service

%files -n  python-%{name}-client
%{python_sitelib}/%{name}/

# apply the right selinux file context
# http://fedoraproject.org/wiki/PackagingDrafts/SELinux#File_contexts

%post
semanage fcontext -a -t rpm_exec_t '%{_datadir}/%{name}/%{name}-system' 2>/dev/null || :
restorecon -R %{_datadir}/%{name}/%{name}-system || :

%postun
if [ $1 -eq 0 ] ; then  # final removal
semanage fcontext -d -t rpm_exec_t '%{_datadir}/%{name}/%{name}-system' 2>/dev/null || :
fi

%files
%doc README.md ChangeLog COPYING
%{_datadir}/dbus-1/system-services/%{dnf_org}*
%{_datadir}/dbus-1/services/%{dnf_org}*
%{_datadir}/%{name}/
%{_datadir}/polkit-1/actions/%{dnf_org}*
# this should not be edited by the user, so no %%config
%{_sysconfdir}/dbus-1/system.d/%{dnf_org}*


%changelog
* Sun Sep 21 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.3.0-1
- bumped release

* Mon Sep 01 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.5-1
- updated ChangeLog (timlau@fedoraproject.org)
- Hack for GObjects dont blow up (timlau@fedoraproject.org)

* Mon Sep 01 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.4-1
- updated ChangeLog (timlau@fedoraproject.org)
- Use GLib mainloop, instead of Gtk, there is crashing in F21
  (timlau@fedoraproject.org)
- use the same cache setup as dnf cli (timlau@fedoraproject.org)
- fix cachedir setup caused by upstream changes (timlau@fedoraproject.org)
- fix: show only latest updates (fixes : timlau/yumex-dnf#2)
  (timlau@fedoraproject.org)
- fix: only get latest upgrades (timlau@fedoraproject.org)

* Sun Jul 13 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.3-1
- fix cachedir setup for dnf 0.5.3 bump dnf dnf requirement
  (timlau@fedoraproject.org)

* Thu May 29 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.2-1
- build: require dnf 0.5.2 (timlau@fedoraproject.org)
- fix refactor issue (timlau@fedoraproject.org)
- api: merged GetPackages with GetPackageWithAttributes.
  (timlau@fedoraproject.org)

* Fri May 09 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.1-1
- bumped release

* Fri May 09 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.2.0-1
- bumped release to 0.2.0


* Fri May 09 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.6-1
- bumped release
* Sat May 03 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.5-1
- work with new dnf 0.5.0 API
* Fri Apr 11 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.4-1
- new package built with tito

* Tue Apr 01 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.4-1
- bumped release to 0.1.4

* Sat Mar 29 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.3-1
- bumped release to 0.1.3

* Mon Mar 24 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.2-1
- bumped release to 0.1.2
- updated requirement to dnf-0.4.19

* Tue Mar 11 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.1-1
- used python3, instead of python2 for dbus services

* Sat Mar 08 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.0-1
- Initial rpm for dnfdaemon
