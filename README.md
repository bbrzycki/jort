# jort
[![PyPI version](https://badge.fury.io/py/jort.svg)](https://badge.fury.io/py/jort) 
[![Documentation Status](https://readthedocs.org/projects/jort/badge/?version=latest)](https://jort.readthedocs.io/en/latest/?badge=latest)

Track, profile, and notify at custom checkpoints in your coding scripts. Time new and existing shell commands with a convenient command line tool. Save and view details of finished jobs with a local database.

## Installation
```
pip install jort
```

## Script Timing
Use the `Tracker` to create named checkpoints throughout your code. Checkpoints need `start` and `stop` calls, and 
multiple iterations are combined to summarize how long it takes to complete each leg. The `report` function
prints the results from all checkpoints. If `stop` is not supplied a checkpoint name, the tracker will close and calculate elapsed time from the last open checkpoint (i.e. last in, first out).
```
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
```

The printed report appears as:
```
my_script | 11.0 s ± 0.0 s per iteration, n = 1
sleep_1s | 1.0 s ± 0.0 s per iteration, n = 10
```

### Function Decorators
`jort` supports timing functions with decorators, via `Tracker.track`. As in the first example:
```
@tr.track
def my_script():
    sleep(1)
    for _ in range(10):
        sleep_1s()
```

## Notifications

Notifications are handled by callbacks to timing functions. As of now, there are three main callbacks:
```
jort.PrintReport()
jort.EmailNotification()
jort.TextNotification()
```
To use notifications, add callbacks to tracking functions:
```
# linear script
tr.stop('my_script', callbacks=[jort.PrintReport(), jort.TextNotification()])

# function decorator
@tr.track(callbacks=[jort.EmailNotification()])
def my_script():
    [...]
```

For SMS text and e-mail notifications, you can enter credentials with the command `jort config`. 

SMS handling is done through Twilio, which offers a [free trial tier](https://support.twilio.com/hc/en-us/articles/223136107-How-does-Twilio-s-Free-Trial-work-). As of now, `jort` handles notifications locally, so you need to add your own credentials for each service. 

## Saving to Database

`jort` allows you to save details of finished jobs to a local database. To save all checkpoints to database, use the `to_db` keyword. You can also optionally group jobs under a common "session" by specifying the `session_name` keyword:
```
tr = jort.Tracker(to_db=True, session_name="my_session")
```
If you do not want every checkpoint to be saved, you can specify manually:
```
tr.stop('my_script', to_db=True)

@tr.track(to_db=True)
def my_script():
    [...]
```

## Command Line Timing

To track a new command, you can run:
```
jort track your_command
```
If the target command uses its own options, place quotes around the full command.
```
jort track "your_command -a -b -c"
```
To send notifications on completion via e-mail or text, add the `-e` or `-t` flags, respectively. For a full list of options, use the `-h` flag.

To save job details to database, add the `-d` flag. You can specify the session name with `-s`, and have `jort` skip jobs that both are already saved in the database under the same session and have completed successfully via the `-u` option.

You can also track an existing process using its integer process ID:
```
jort track PID
```
Similarly, add the `-e` or `-t` flags for either e-mail or SMS notification on completion, and `-d` and `-s` flags for saving info to database.

## Future Directions

* Save runtimes and other details in persistent format
* Potential support for more complex profiling
* Offer a centralized option for notification handling
