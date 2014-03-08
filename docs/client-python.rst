==========================================
Client API for Python 2.x and 3.x
==========================================

.. automodule:: dnfdaemon

Classes
========

System API
-------------

.. autoclass:: dnfdaemon.DnfDaemonClient
    :members: Exit, Lock, Unlock, SetWatchdogState,GetPackageWithAttributes, GetRepositoriesGetRepo, GetConfig, SetConfig,
    		  GetAttribute, GetUpdateInfo, GetPackages, GetPackagesByName, GetHistoryByDays, HistorySearch, GetHistoryPackages,
    		  GetGroups, Search, ClearTransaction, GetTransaction, AddTransaction, Install, Remove, Update, Reinstal, Downgrade,
    		  BuildTransaction, RunTransaction, GetEnabledRepos, GetGroupPackages, ConfirmGPGImport
    
Session API
------------

.. autoclass:: dnfdaemon.DnfDaemonReadOnlyClient
    :members: Exit, Lock, Unlock, SetWatchdogState,GetPackageWithAttributes, GetRepositoriesGetRepo, GetConfig, 
    		  GetAttribute, GetUpdateInfo, GetPackages, GetPackagesByName, GetGroups, Search
    		  BuildTransaction, RunTransaction, GetEnabledRepos, GetGroupPackages
    
Exceptions
============

.. class:: DaemonError(Exception)

Base Exception from the backend

.. class:: AccessDeniedError(DaemonError)

PolicyKit access was denied.

Ex.
User press cancel button in policykit window

.. class:: LockedError(DaemonError)

dnf is locked by another application

Ex.
dnf is running in a another session
You have not called the Lock method to grep the Lock


.. class:: TransactionError(DaemonError)

Error in the dnf transaction.

