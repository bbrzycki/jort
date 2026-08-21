Public interfaces
=================

This page is the canonical inventory of Jort's user-facing interfaces. Check
these interfaces before proposing a new command runner or notification API.

Python command execution
------------------------

Use :code:`jort.track_new` to run and track a new command. Email and SMS are
independent options, so either or both can be enabled:

.. code-block:: python

    import jort

    payload = jort.track_new(
        "pytest -q",
        send_email=True,
        send_text=True,
    )

The function is exported at the package top level. It accepts a command string,
supports shell execution with :code:`use_shell=True`, and returns the completed
job payload.

For Python code that already manages its own timing blocks, use the existing
callbacks instead:

.. code-block:: python

    tracker.stop(
        callbacks=[jort.EmailNotification(), jort.TextNotification()]
    )

Command-line execution
----------------------

Use :code:`jort track` from any project directory. The notification options are
independent and can be combined:

.. code-block:: bash

    jort track --email --text 'pytest -q'

Use :code:`--shell` when the job is a shell expression involving commands,
pipelines, redirects, or shell built-ins such as :code:`cd`:

.. code-block:: bash

    jort track --email --shell 'cd /path/to/project && make test'

The path above is intentionally a placeholder; documentation and tests should
not contain machine-specific paths.

Notification configuration
--------------------------

Email and SMS credentials are configured locally with :code:`jort config email`
and :code:`jort config text`. The command runner selects channels with
the flags above; it does not require a separate notification API.

Implementation map
------------------

* Package exports: :code:`jort/__init__.py`
* CLI options and dispatch: :code:`jort/jort_exe.py`
* New-process tracking: :code:`jort/track_cli.py`
* Python timing and callback dispatch: :code:`jort/tracker.py`
* Email and SMS implementations: :code:`jort/reporting_callbacks.py`
* Public-interface regression tests: :code:`tests/test_public_contract.py`
