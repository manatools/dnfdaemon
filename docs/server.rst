==========================================
DBus service API documentation
==========================================

The dnfdaemon is an easy way to utililize the power of the dnf package manager from your own programs

Data structures
----------------

.. table:: **Data structures**

   =================================  =================================
   Name                               Content
   =================================  =================================
   Package Id (pkg_id)                "name,epoch,ver,rel,arch,repo_id"
   =================================  =================================

|

.. table:: **Attribute Descriptions**

   ================  =========================================================
   Attribute         Description
   ================  =========================================================
   name              Package Name
   epoch             Package Epoch
   ver               Package Version
   rel               Package Release
   arch				 Package Architecture
   repo_id			 Repository Id
   ================  =========================================================

Transaction result::

	<transaction_result> ::= <result>, <result>, ...., <result>
	<result>             ::= <action>, <pkg_list>
	<action>             ::= install | update | remove | reinstall | downgrade | obsolete
	<plg_list>           ::= <pkg_info>, <pkg_info>, ......, <pkg_info>
	<pkg_info>           ::= <pkg_id>, size, <obs_list>
	<pkg_id>             ::= name, epoch, version, release, arch, repo_id
	<obs_list>           ::= <obs_id>, <obs_id>, ...., <obs_id>
	<obs_id>             ::= name, epoch, version, release, arch, repo_id for packages obsoletes by <pkg_id>


==========================================
System Service
==========================================

.. table:: **DBus Names**

   ========================  =========================================================
   Attribute				 Value	
   ========================  =========================================================
   object                    org.baseurl.DnfSystem
   interface                 org.baseurl.DnfSystem
   path                      /
   ========================  =========================================================

Misc methods
-------------

.. function:: GetVersion()

   Get the API version

   :return: string with API version

.. function:: Lock()

   Get the daemon Lock, if posible

.. function:: Unlock()

   Release the daemon Lock, if posible

.. function:: SetWatchdogState(state)

   Set the Watchdog state.
   if watchdog is enabled, then daemon will exit not used in 20s.

   :param state: True = Watchdog active, False = Watchdog disabled
   :type state: boolean (b)

Repository and config methods
------------------------------

.. py:function:: GetRepositories(filter)

   Get the value a list of repo ids

   :param filter: filter to limit the listed repositories
   :type filter: string
   :return: list of repo id's
   :rtype: array for stings (as)

.. py:function:: GetRepo(repo_id)

   Get information about a give repo_id

   :param repo_id: repo id
   :type repo_id: string
   :return: a dictionary with repo information **(JSON)**
   :rtype: string (s)

.. py:function:: SetEnabledRepos(repo_ids):

   Enabled a list of repositories, disabled all other repos

   :param repo_ids: list of repo ids to enable


.. py:function:: GetConfig(setting)

   Get the value of a yum config setting

   :param setting: name of setting (debuglevel etc..)
   :type setting: string
   :return: the config value of the requested setting **(JSON)**
   :rtype: string (s)

.. py:function:: SetConfig(setting, value)

   Get the value of a yum config setting

   :param setting: name of setting (debuglevel etc..)
   :type setting: string
   :param value: name of setting (debuglevel etc..)
   :type value: misc types **(JSON)**
   :return: did the update succed
   :rtype: boolean (b)

.. py:function:: ExpireCache()

   Expire the dnf cache, to force dnf to check for updated metadata.



Package methods
----------------

These methods is for getting packages and information about packages


.. function:: GetPackages(pkg_filter, fields)

   | Get a list of pkg list for a given package filter
   | each pkg list contains [pkg_id, field,....] where field is a atrribute of the package object
   | Ex. summary, size etc.
   | if no extra fields values are needed just use a empty array []
	
   :param pkg_filter: package filter ('installed','available','updates','obsoletes','recent','extras')
   :type pkg_filter: string
   :param fields: yum package objects attributes to get.
   :type fields: array of strings (as)
   :return: list of (id, field1, field2...) **(JSON)**, each JSON Sting contains (id, field1, field2...)
   :rtype: array of strings (as)

.. py:function:: GetPackagesByName(name, attrs, newest_only)

   Get a list of pkg ids for starts with name and some user defined attributes

   :param name: name prefix to match
   :type name: string
   :param attrs: a list of packages attributes to return
   :type attrs: list of strings
   :param newest_only: show only the newest match or every match.
   :type newest_only: boolean
   :return: list of pkg_id or [pkg_id, attr1, attr2, ....] if attrs is set
   :rtype: array of strings (as)


.. py:function:: GetAttribute(id, attr,)

   get yum package attribute (description, filelist, changelog etc)

   :param pkg_id: pkg_id to get attribute from
   :type pkg_id: string
   :param attr: name of attribute to get
   :type attr: string
   :return: the value of the attribute **(JSON)**, the content depend on attribute being read
   :rtype:  string (s)

.. py:function:: Search(fields, keys, attrs, match_all, newest_only, tags )

   Search for packages where keys is matched in fields and return extra attributes

   :param fields: yum po attributes to search in
   :type fields: array of strings
   :param keys: keys to search for
   :type keys: array of strings
   :param attrs: list of extra package attributes to get
   :param match_all: match all keys or only one
   :type match_all: boolean
   :param newest_only: match all keys or only one
   :type newest_only: boolean
   :param tags: search in pkgtags
   :type tags: boolean
   :return: list of [pkg_id, attr1, attr2, ..] **JSON**
   :rtype: string (s)

High level methods
-------------------
The high level methods simulate basic dnf command line main functions.

.. py:function:: Install(cmds)

Works just like the ``dnf install <cmds>`` command line

   :param cmds: package arguments separated by spaces
   :type cmds: string
   :return: return code, result of resolved transaction (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)

.. py:function:: Remove(cmds)

   Works just like the ``dnf remove <cmds>`` command line

   :param cmds: package arguments separated by spaces
   :type cmds: string
   :return: return code, result of resolved transaction (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)


.. py:function:: Update(cmds)

   Works just like the ``dnf update <cmds>`` command line

   :param cmds: package arguments separated by spaces
   :type cmds: string
   :return: return code, result of resolved transaction (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)


.. py:function:: Reinstall(cmds)

   Works just like the ``dnf reinstall <cmds>`` command line

   :param cmds: package arguments separated by spaces
   :type cmds: string
   :return: return code, result of resolved transaction (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)


.. py:function:: Downgrade(cmds)

   Works just like the ``dnf downgrade <cmds>`` command line

   :param cmds: package arguments separated by spaces
   :type cmds: string
   :return: return code, result of resolved transaction (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)



Transaction methods
--------------------
These methods is for handling the current yum transaction

.. py:function:: AddTransaction(id, action)

   Add an package to the current transaction

   :param id: package id for the package to add
   :type id: string
   :param action: the action to perform ( install, update, remove, obsolete, reinstall, downgrade, localinstall )
   :type action: string
   :return: list of (pkg_id, transaction state) pairs for the added members (comma separated)
   :rtype: array of strings (as)

.. py:function:: ClearTransaction()

   Clear the current transaction

.. py:function:: GetTransaction()

   Get the currrent transaction

   :return: list of (pkg_id, transaction state) pairs in the current transaction (comma separated)
   :rtype: array of strings (as)

.. py:function:: BuildTransaction()

   Depsolve the current transaction

   :return: (return code, result of resolved transaction) pair (rc = 1 is ok, else failure) **(JSON)**
   :rtype: string (s)

	
.. py:function:: RunTransaction()

   Execute the current transaction

   :return:  (rc,msg) rc = state of run transaction (0 = ok, 1 = need GPG import confirmation, 2 = error) and msgs =  list of error messages **(JSON)**
   :rtype: string (s)

.. py:function:: ConfirmGPGImport(self, hexkeyid, confirmed)

   Confirm import of at GPG Key by yum

   :param hexkeyid: hex keyid for GPG key
   :type hexkeyid: string (s)
   :param confirmed: confirm import of key (True/False)
   :type confirmed: boolean (b)


Groups
-------

Methods to work with yum groups and categories

.. py:function:: GetGroups( )

   Get available Categories & Groups

.. py:function:: GetGroupPackages(grp_id, grp_flt )

   Get packages in a group by grp_id and grp_flt

   :param grp_id: The Group id
   :type grp_id: string (s)
   :param grp_flt: Group Filter (all or default)
   :type grp_flt: string (s)
   :return: list of pkg_id's
   :rtype: array of strings (as)


.. py:function:: GroupInstall(patterns)

   Install groups matching patterns

   :param patterns: patterns separated by ' ' (ex. "firefox xfce-desktop")

.. py:function:: GroupRemove(patterns)

   Removing groups matching patterns

   :param patterns: patterns separated by ' ' (ex. "firefox xfce-desktop")


.. note:: Under Development

   More to come in the future, methods to install groups etc. has to be defined and implemented

History
--------

Methods to work with the package transaction history

.. py:function:: GetHistoryByDays(start_days, end_days)

        Get History transaction in a interval of days from today

        :param start_days: start of interval in days from now (0 = today)
        :type start_days: integer
        :param end_days: end of interval in days from now
        :type end_days: integer
        :return: a list of (transaction ids, date-time) pairs (JSON)
		:rtype: string (s)

.. py:function:: GetHistoryPackages(tid)

        Get packages from a given yum history transaction id

        :param tid: history transaction id
        :type tid: integer
        :return: list of (pkg_id, state, installed) pairs
        :rtype: json encoded string

.. py:function:: HistorySearch(pattern)

        Search the history for transaction matching a pattern

        :param pattern: patterne to match
        :type pattern: string
        :return: list of (tid,isodates)
        :type sender: json encoded string

Signals
--------

.. py:function:: TransactionEvent(self,event,data):

        Signal with Transaction event information, telling the current step in the processing of
        the current transaction.

        Steps are : start-run, download, pkg-to-download, signature-check, run-test-transaction, run-transaction, verify, fail, end-run

        :param event: current step


.. py:function:: RPMProgress(self, package, action, te_current, te_total, ts_current, ts_total):

        signal with RPM Progress

        :param package: A package object or simple string of a package name
        :param action: action current performed on the package: install, cleanup, remove etc.
        :param te_current: Current number of bytes processed in the transaction
                           element being processed
        :param te_total: Total number of bytes in the transaction element being
                         processed
        :param ts_current: number of processes completed in whole transaction
        :param ts_total: total number of processes in the transaction.


.. py:function:: GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp ):

        signal with GPG Key information of a key there need to be confirmed to complete the
        current transaction. after signal is send transaction will abort with rc=1
        Use ConfirmGPGImport method to comfirm the key and run RunTransaction again


        :param pkg_id: pkg_id for the package needing the GPG Key to be verified
        :param userid: GPG key name
        :param hexkeyid: GPG key hex id
        :param keyurl: Url to the GPG Key
        :param timestamp: GPG Timestamp

.. py:function::  ErrorMessage(self, error_msg)

   An error message from the backend

   :param error_msg: error message (s)


.. py:function::  DownloadStart(self, num_files, num_bytes)

   Starting a new parallel download batch

   :param num_files: number of files to download
   :param num_bytes: number of bytes to download

.. py:function:: DownloadProgress(self, name, frac, total_frac, total_files)

   Progress for a single instance in the batch

   :param name: name of package
   :param frac: fraction downloaded (0.0 -> 1.0)
   :param total_frac: fraction downloaded of whole batch(0.0 -> 1.0)
   :param total_files: total files downloaded

.. py:function:: DownloadEnd(self, name, status, msg)

   Download of af single instace ended

   :param name: name of package
   :param status: download status
   :param msg: error message, if status != ok

.. py:function:: RepoMetaDataProgress(self, name, frac)

   Repository Metadata Download progress

   :param name: repository id
   :param frac: fraction downloaded (0.0 -> 1.0)


==========================================
Session Service
==========================================
.. table:: **DBus Names**

   ========================  =========================================================
   Attribute				 Value	
   ========================  =========================================================
   object                    org.baseurl.DnfSession
   interface                 org.baseurl.DnfSession
   path                      /
   ========================  =========================================================



Misc methods
-------------

.. function:: GetVersion()

   Get the API version

   :return: string with API version

.. function:: Lock()

   Get the daemon Lock, if posible

.. function:: Unlock()

   Release the daemon Lock, if posible

Repository and config methods
------------------------------

.. py:function:: GetRepositories(filter)

   Get the value a list of repo ids

   :param filter: filter to limit the listed repositories
   :type filter: string
   :return: list of repo id's
   :rtype: array for stings (as)

.. py:function:: GetRepo(repo_id)

   Get information about a give repo_id

   :param repo_id: repo id
   :type repo_id: string
   :return: a dictionary with repo information **(JSON)**
   :rtype: string (s)

.. py:function:: SetEnabledRepos(repo_ids):

   Enabled a list of repositories, disabled all other repos

   :param repo_ids: list of repo ids to enable

.. py:function:: GetConfig(setting)

   Get the value of a yum config setting

   :param setting: name of setting (debuglevel etc..)
   :type setting: string
   :return: the config value of the requested setting **(JSON)**
   :rtype: string (s)

Package methods
----------------

These methods is for getting packages and information about packages

.. function:: GetPackages(pkg_filter)

   get a list of packages matching the filter type

   :param pkg_filter: package filter ('installed','available','updates','obsoletes','recent','extras')
   :type pkg_filter: string
   :return: list of pkg_id's
   :rtype: array of strings (as)



.. function:: GetPackageWithAttributes(pkg_filter, fields)

   | Get a list of pkg list for a given package filter
   | each pkg list contains [pkg_id, field,....] where field is a atrribute of the package object
   | Ex. summary, size etc.
	
   :param pkg_filter: package filter ('installed','available','updates','obsoletes','recent','extras')
   :type pkg_filter: string
   :param fields: yum package objects attributes to get.
   :type fields: array of strings (as)
   :return: list of (id, field1, field2...) **(JSON)**, each JSON Sting contains (id, field1, field2...)
   :rtype: array of strings (as)

.. py:function:: GetPackagesByName(name, attrs, newest_only)

   Get a list of pkg ids for starts with name and some user defined attributes

   :param name: name prefix to match
   :type name: string
   :param attrs: a list of packages attributes to return
   :type attrs: list of strings
   :param newest_only: show only the newest match or every match.
   :type newest_only: boolean
   :return: list of pkg_id or [pkg_id, attr1, attr2, ....] if attrs is set
   :rtype: array of strings (as)


.. py:function:: GetAttribute(id, attr,)

   get yum package attribute (description, filelist, changelog etc)

   :param pkg_id: pkg_id to get attribute from
   :type pkg_id: string
   :param attr: name of attribute to get
   :type attr: string
   :return: the value of the attribute **(JSON)**, the content depend on attribute being read
   :rtype:  string (s)

.. py:function:: Search(fields, keys, attrs, match_all, newest_only, tags )

   Search for packages where keys is matched in fields and return extra attributes

   :param fields: yum po attributes to search in
   :type fields: array of strings
   :param keys: keys to search for
   :type keys: array of strings
   :param attrs: list of extra package attributes to get
   :param match_all: match all keys or only one
   :type match_all: boolean
   :param newest_only: match all keys or only one
   :type newest_only: boolean
   :param tags: search in pkgtags
   :type tags: boolean
   :return: list of pkg_id or [pkg_id, attr1, attr2, ..] if attr is defined **JSON**
   :rtype: string (s)

Groups
-------

Methods to work with dnf groups and categories

.. py:function:: GetGroups( )

   Get available Categories & Groups

.. py:function:: GetGroupPackages(grp_id, grp_flt )

   Get packages in a group by grp_id and grp_flt

   :param grp_id: The Group id
   :type grp_id: string (s)
   :param grp_flt: Group Filter (all or default)
   :type grp_flt: string (s)
   :return: list of pkg_id's
   :rtype: array of strings (as)

.. note:: Under Development

   More to come in the future, methods to install groups etc. has to be defined and implemented

Signals
--------

.. note:: Under Development

   Signals is not documented yet
