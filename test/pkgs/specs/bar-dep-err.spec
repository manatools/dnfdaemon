%global pkg_ver 1.0

Name:           bar-dep-error
Version:        %{pkg_ver}
Release:        1%{?dist}
Summary:        foo-dep-err test package for dnf-daemon testing

License:        GPLv2+
URL:            https://github.com/timlau/dnf-daemon
Source0:        source.tar.gz
BuildArch:      noarch
Requires:		not-found-bar-dep

%description
foo-dep-err test package for dnf-daemon testing

%prep
%setup -q -n source


%build
# Nothing to build

%install
# Nothing to install

%files
%doc README

%changelog
* Mon Mar 10 2014 Tim Lauridsen <timlau@fedoraproject.org>
- Initial RPM
