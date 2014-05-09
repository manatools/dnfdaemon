PYTHON3=python3
PACKAGE = dnfdaemon/server
PYFILES = $(wildcard *.py)
PYVER3 := $(shell $(PYTHON3) -c 'import sys; print("%.3s" %(sys.version))')
PYSYSDIR3 := $(shell $(PYTHON3) -c 'import sys; print(sys.prefix)')
PYLIBDIR3 = $(PYSYSDIR3)/lib/python$(PYVER3)
PKGDIR3 = $(PYLIBDIR3)/site-packages/$(PACKAGE)

all: 
	echo "Nothing to do"

clean:
	rm -rf *.pyc *.pyo *~ __pycache__/
	

install:
	mkdir -p $(DESTDIR)/$(PKGDIR3)
	for p in $(PYFILES) ; do \
		install -m 644 $$p $(DESTDIR)/$(PKGDIR3)/$$p; \
	done
