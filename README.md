23-03-2017: dnf-daemon if no longer under active development
============================================================

dnf-daemon
===========

dnf-daemon is a 2 DBus services there make part for dnf's API available for application via DBus calls.

There is a DBus session bus service runnning as current user for performing readonly actions.

There is a DBus system bus service runnning as root for performing actions there is making changes to the system

This make it easy to do packaging action from your application no matter what language it is written in, as long as there
is DBus binding for it.

dnf-daemon uses PolicyKit for authentication for the system service, so when you call one of the commands (as normal users) you will get a  
PolicyKit dialog to ask for password of a priviledged user like root.

**dnf-daemon is still under heavy development and the API is not stable or complete yet**

Source overview
----------------

    dnfdaemon/      Contains the daemon python source
    client/         Contains the client API bindings for python 2.x & 3.x
    test/           Unit test for the daemon and python bindings
    dbus/           DBus system service setup files
    policykit1/     PolicyKit authentication setup files



How to install services and python bindings:
-----------------------------------------------

Run the following

```
	git clone ...
	cd dnf-daemon
	make test-inst
```


How to test:
-------------

just run:
   
    make test-verbose

to run the unit test with output to console

or this to just run the unit tests.

    make test
   
To make the daemons shutdown
-------------------------------

Session:
	
	make exit-session
	
System
	
	make exit-system
	
Both

    make exit-both
   

to run the daemons in debug mode from checkout:
------------------------------------------------

session (readonly as current user)

	make run-session

system (as root)
	
	make run-system


API Definitions: 
====================================

The dnfdaemon api is documented [here](http://dnf-daemon.readthedocs.org/en/latest/index.html)

The API is under development, so it might change, when we hit version 1.0, API methods will be frozen and
API method names, parameters and return types will not change in future releases, new API can be added,
but the old ones stays as is



API Addition Checklist: 
====================================
* Add the new API methods to dnfdaemon-system.py and optional dnfdaemon-session.py
* Add client api method in DnfDaemonBase if it is available in both daemon
  or in DnfDaemonClient is it is a system only api.
* Add unit tests for the api in test/test-system-api.py and optional to test/test-system-api.py if it exists in the session api
* Update docs/server.rst and docs/client-python.api ( add new api method to members )
* All unit tests must pass (make test) before pushing to github

