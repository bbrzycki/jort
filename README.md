# jort
[![PyPI version](https://badge.fury.io/py/jort.svg)](https://badge.fury.io/py/jort) 
[![Documentation Status](https://readthedocs.org/projects/jort/badge/?version=latest)](https://jort.readthedocs.io/en/latest/?badge=latest)

Track, profile, and notify at custom checkpoints in your coding scripts. Time new and existing shell commands with a convenient command line tool. 

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
jort.SMSNotification()
```
To use notifications, add callbacks to tracking functions:
```
# linear script
tr.stop('my_script', callbacks=[jort.PrintReport(), jort.SMSNotification()])

# function decorator
@tr.track(callbacks=[jort.EmailNotification()])
def my_script():
    [...]
```

For SMS and e-mail notifications, you can enter credentials with the command `jort -i`. 

SMS handling is done through Twilio, which offers a [free trial tier](https://support.twilio.com/hc/en-us/articles/223136107-How-does-Twilio-s-Free-Trial-work-). As of now, `jort` handles notifications locally, so you need to add your own credentials for each service. 

## Command Line Timing

To track a new command, use the `-c` flag:
```
jort -c your_command
```
If the target command uses its own flags, place quotes around the full command.
```
jort -c "your_command -a -b -c"
```
To send notifications on completion via e-mail or SMS, add the `-e` or `-s` flags, respectively. 

You can also track an existing process using its process ID:
```
jort -p PID
```
Similarly, add the `-e` or `-s` flags for either e-mail or SMS notification on completion. 

## Future Directions

* Save runtimes and other details in persistent format
* Potential support for more complex profiling
* Offer a centralized option for notification handling
