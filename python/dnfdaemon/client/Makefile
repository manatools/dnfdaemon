PYTHON2=python2
PYTHON3=python3
PACKAGE = dnfdaemon/client
PYFILES = $(wildcard *.py)
PYVER2 := $(shell $(PYTHON2) -c 'import sys; print("%.3s" %(sys.version))')
PYSYSDIR2 := $(shell $(PYTHON2) -c 'import sys; print(sys.prefix)')
PYLIBDIR2 = $(PYSYSDIR2)/lib/python$(PYVER2)
PKGDIR2 = $(PYLIBDIR2)/site-packages/$(PACKAGE)
PYVER3 := $(shell $(PYTHON3) -c 'import sys; print("%.3s" %(sys.version))')
PYSYSDIR3 := $(shell $(PYTHON3) -c 'import sys; print(sys.prefix)')
PYLIBDIR3 = $(PYSYSDIR3)/lib/python$(PYVER3)
PKGDIR3 = $(PYLIBDIR3)/site-packages/$(PACKAGE)

all: 
	echo "Nothing to do"

clean:
	rm -rf *.pyc *.pyo *~ __pycache__/
	

install:
	mkdir -p $(DESTDIR)/$(PKGDIR2)
	mkdir -p $(DESTDIR)/$(PKGDIR3)
	for p in $(PYFILES) ; do \
		install -m 644 $$p $(DESTDIR)/$(PKGDIR2)/$$p; \
		install -m 644 $$p $(DESTDIR)/$(PKGDIR3)/$$p; \
	done
