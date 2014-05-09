SUBDIRS = dnfdaemon dnfdaemon/server dnfdaemon/client 

all: subdirs
	
subdirs:
	for d in $(SUBDIRS); do make -C $$d; [ $$? = 0 ] || exit 1 ; done

clean:
	for d in $(SUBDIRS); do make -C $$d clean ; done
	
install:
	for d in $(SUBDIRS); do make DESTDIR=$(DESTDIR) -C $$d install; [ $$? = 0 ] || exit 1; done


FORCE:
	
