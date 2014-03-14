#!/bin/bash
# cleanup
rm -f dnf-daemon-test.repo
rm -rf repo/
# setup & build the rpms
cp source.tar.gz ~/rpmbuild/SOURCES
rpmbuild -ba specs/foo-10.spec
rpmbuild -ba specs/foo-20.spec
rpmbuild -ba specs/bar-10.spec
rpmbuild -ba specs/bar-20.spec
rpmbuild -ba specs/foobar-10.spec
rpmbuild -ba specs/foobar-20.spec
rpmbuild -ba specs/foo-dep-err.spec
rpmbuild -ba specs/bar-dep-err.spec
rpmbuild -ba specs/bar-old.spec
rpmbuild -ba specs/bar-new.spec
# create the repo and install a .repo files
mkdir repo
cp ~/rpmbuild/RPMS/noarch/foo*.rpm ./repo/
cp ~/rpmbuild/RPMS/noarch/bar*.rpm ./repo/
createrepo -d repo/.
rm -f dnf-daemon-test.repo
cat <<- EOF > dnf-daemon-test.repo
[dnf-daemon-test]
name=dnf-daemon test repo
baseurl=file://$PWD/repo/
gpgcheck=0
enabled=1
EOF
sudo cp dnf-daemon-test.repo /etc/yum.repos.d/.

