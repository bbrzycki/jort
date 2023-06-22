Python script timing
====================

Basic usage
-----------

The main tracking functionality uses the :code:`Tracker` object, which is used to
create named checkpoints throughout your code. Checkpoints need :code:`start` and 
:code:`stop` calls, and multiple iterations are combined to summarize how long it takes 
to complete each leg. The :code:`report` function prints the results from all checkpoints. 
If :code:`stop` is not supplied a checkpoint name, the tracker will close and calculate 
elapsed time from the last open checkpoint (i.e. last in, first out).

As an example of the basic usage:

.. code-block:: Python

    import jort
    from time import sleep

    tr = jort.Tracker()

    tr.start('my_script')
    sleep(1)
    for _ in range(10):
        tr.start('sleep_1s')
        sleep(1)
        tr.stop('sleep_1s')
    tr.stop('my_script')
        
    tr.report()

The printed report appears as:

.. code-block:: Python

    my_script | 11.0 s ± 0.0 s per iteration, n = 1
    sleep_1s | 1.0 s ± 0.0 s per iteration, n = 10


Notifications
-------------

Notifications are handled by callbacks to timing functions. As of now, there are three 
main callbacks:

.. code-block:: Python

    jort.PrintReport()
    jort.EmailNotification()
    jort.TextNotification()

Notifications are executed at the end of checkpoints using the function
:code:`Tracker.stop` with argument :code:`callbacks`, which accepts a list of 
callbacks. Note: notification callbacks are not intended to be called frequently.

If used in the callback of a :code:`jort` :ref:`function decorator <funcdec>`  or 
:ref:`command line tracker <cli>`, the tracker will flag errors and print the appropriate message.

.. code-block:: Python

    tr = jort.Tracker()
    tr.start()
    # your code here
    tr.stop(callbacks=[jort.PrintReport(), jort.EmailNotification(), jort.TextNotification()])


:code:`PrintReport`
^^^^^^^^^^^^^^^^^^^

:code:`PrintReport` prints a formatted completion message with the runtime. 

.. code-block:: Python 

    tr.stop(callbacks=[jort.PrintReport()])

:code:`EmailNotification`
^^^^^^^^^^^^^^^^^^^^^^^^^

:code:`EmailNotification` e-mails a formatted message with the runtime and
other job details. If used to time a command line program, this callback can be used
to send program output as an e-mail attachment.

Of course, to send e-mails from your account, you will need to enter login credentials
with the command line tool :code:`jort config`. For e-mail, :code:`jort` needs the SMTP server 
(for Gmail this is `smtp.gmail.com`), your e-mail, and either a password
or app password. At the moment, you can only send notification e-mails to yourself, from
your own account.

.. code-block:: Python 

    tr.stop(callbacks=[jort.EmailNotification()])

:code:`TextNotification`
^^^^^^^^^^^^^^^^^^^^^^^

:code:`TextNotification` texts a formatted message with the runtime. :code:`jort` uses 
Twilio to handle SMS messaging. Twilio offers a `free trial tier <https://support.twilio.com/hc/en-us/articles/223136107-How-does-Twilio-s-Free-Trial-work->`_.

You will need to enter login credentials with the command line tool :code:`jort config`. 
For SMS, :code:`jort` needs your phone number (to receive notifications), your Twilio
number, account SID, and auth token. If you are using the free trial, you may only send 
SMS messages to verified phone numbers on your Twilio account.

.. code-block:: Python 

    tr.stop(callbacks=[jort.TextNotification()])

.. _funcdec:

Function decorators
-------------------

:code:`jort` supports timing functions with decorators, via :code:`Tracker.track`. 
Demonstrating on the first example:

.. code-block:: Python

    tr = jort.Tracker()

    @tr.track
    def sleep_1s():
        sleep(1)
        
    @tr.track
    def my_script():
        sleep(1)
        for _ in range(10):
            sleep_1s()

    my_script() 
    tr.report()

The printed report appears as:

.. code-block:: Python

    my_script | 11.0 s ± 0.0 s per iteration, n = 1
    sleep_1s | 1.0 s ± 0.0 s per iteration, n = 10

You can use notification callbacks (once again, it may not be useful to notify
on functions that execute many times):

.. code-block:: Python

    @tr.track(callbacks=[jort.EmailNotification()])
    def my_script():
        sleep(1)
        for _ in range(10):
            sleep_1s()

If you want to time one-off functions, you can also use :code:`jort.track` without
instantiating a :code:`Tracker`:

.. code-block:: Python

    @jort.track
    def my_script():
        sleep(1)
        for _ in range(10):
            sleep_1s()

Saving to database 
------------------

`jort` allows you to save details of finished jobs to a local database. To save all 
checkpoints to database, use the :code:`to_db` keyword. You can also optionally group jobs 
under a common "session" by specifying the :code:`session_name` keyword:

.. code-block:: Python

    tr = jort.Tracker(to_db=True, session_name="my_session")

If you do not want every checkpoint to be saved, you can specify manually:

.. code-block:: Python

    tr.stop('my_script', to_db=True)

    @tr.track(to_db=True)
    def my_script():
        [...]

Logging
-------

:code:`jort` automatically logs results by default. You can change the destination filename,
as well as the level of verbosity (0: no logging; 1: only elapsed times; 
2: start and stop times). Defaults are :code:`logname='tracker.log'` and :code:`verbose=2`.

.. code-block:: Python

    import jort
    from time import sleep

    tr = jort.Tracker(logname='my_log.log', verbose=1)
