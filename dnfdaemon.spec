%global dnf_org org.baseurl.Dnf

Name:           dnfdaemon
Version:        0.1.1
Release:        1%{?dist}
Summary:        DBus daemon for dnf package actions
License:        GPLv2+
URL:            https://github.com/timlau/dnf-daemon
Source0:        https://fedorahosted.org/releases/y/u/yumex/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python2-devel
Requires:       dbus-python
Requires:       dnf >= 0.4.17
Requires:       polkit
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
Summary:        Python 3 api for communicating with the dnf-daemon DBus service
Group:          Applications/System
BuildRequires:  python3-devel
Requires:       %{name} = %{version}-%{release}
Requires:       python3-gobject

%description -n python3-%{name}
Python 3 api for communicating with the dnf-daemon DBus service

%files -n  python3-%{name}
%{python3_sitelib}/%{name}/

%package -n python-%{name}
Summary:        Python 2 api for communicating with the dnf-daemon DBus service
Group:          Applications/System
BuildRequires:  python2-devel
Requires:       %{name} = %{version}-%{release}
Requires:       pygobject3

%description -n python-%{name}
Python 2 api for communicating with the dnf-daemon DBus service

%files -n  python-%{name}
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
* Tue Mar 11 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.1-1
- bumped release

* Sat Mar 08 2014 Tim Lauridsen <timlau@fedoraproject.org> 0.1.0-1
- Initial rpm for dnfdaemon
