.. _cli:

Command line tracking
=====================

Upon installation, Jort provides a command line utility :code:`jort` to help track
programs at the command line. 

Track new command 
-----------------

To track a new command, use the :code:`-c` flag:

.. code-block:: bash

    jort -c your_command

If the target command uses its own flags, place quotes around the full command.

.. code-block:: bash

    jort -c "your_command -a -b -c"

To send notifications on completion via e-mail or SMS, add the :code:`-e` or :code:`-s` 
flags, respectively. Note that both methods require appropriate login credentials, 
which can be entered at the command line using :code:`jort -i`. 

The :code:`jort` tool spawns a subprocess with your command, so it can capture all 
stdout/stderr output. You can save this output and send as a :code:`.txt` attachment
to an e-mail notification by adding the flag :code:`-o` (in addition to the e-mail flag). 

Track existing process 
----------------------

You can also track an existing process using its process ID:

.. code-block:: bash

    jort -p PID

Similarly, add the :code:`-e` or :code:`-s` flags for either e-mail or SMS notification
on completion. Note that since :code:`jort` was not the parent process, it can't save 
output or flag errors. 