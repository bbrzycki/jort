.. _cli:

Command line tracking
=====================

Upon installation, Jort provides a command line utility :code:`jort` to help track
programs at the command line. 

Track new command
-----------------

To track a new command, you can run:

.. code-block:: bash

    jort track your_command

If the target command uses its own options, place quotes around the full command.

.. code-block:: bash

    jort track "your_command -a -b -c"

To send notifications on completion via e-mail or SMS, add the :code:`-e` or :code:`-t` 
flags, respectively. Note that both methods require appropriate login credentials, 
which can be entered at the command line using :code:`jort config`. 

To save job details to database, add the :code:`-d` flag. You can specify the session name 
with :code:`-s`, and have :code:`jort` skip jobs that both are already saved in the database under 
the same session and have completed successfully via the :code:`-u` option.

For agent integrations, :code:`--json` returns a machine-readable payload and
:code:`--detach` moves monitoring into a background worker that survives the
calling terminal:

.. code-block:: bash

    jort track --detach --email --json 'python benchmark.py'
    jort status JOB_ID --json
    jort logs JOB_ID

The command exits nonzero when a newly tracked command exits nonzero. Use
:code:`jort doctor` to validate configuration without sending anything, and
:code:`jort notify test --email` or :code:`--text` to test a provider.
Use :code:`--timeout SECONDS` to bound execution and :code:`--strict-notifications`
to return exit code 2 when a requested channel fails. Use :code:`--argv --`
when exact argument preservation is required.

The :code:`jort` tool spawns a subprocess with your command, so it can capture all 
stdout/stderr output. You can save this output and send as a :code:`.txt` attachment
to an e-mail notification by adding the flag :code:`-o` (in addition to the e-mail flag). 

Track existing process
----------------------

You can also track an existing process using its integer process ID:

.. code-block:: bash

    jort track PID

Similarly, add the :code:`-e` or :code:`-t` flags for either e-mail or SMS notification
on completion, and :code:`-d` and :code:`-s` flags for saving info to database. Note 
that since :code:`jort` was not the parent process, it can't save output or flag errors.

Local monitoring dashboard
--------------------------

Use the local dashboard for a concise view of active jobs and recent history
without rendering a build's full output in an editor terminal:

.. code-block:: bash

    jort dashboard

The command starts a loopback-only server, opens a browser, and prints its
local capability URL. It refreshes active job state once per second and shows
captured output only as a bounded tail when selected. It never uploads job
data. Use :code:`--no-open` to suppress browser launch, :code:`--port` to
choose a local port, and :code:`--history-limit` to bound the history view.

For a job's output to be available live, launch it with :code:`jort track
--output`; output is line-buffered and capped by :code:`--max-output-bytes`.
Detached jobs write a durable running heartbeat while executing, including
aggregate process-tree memory and CPU metrics.
