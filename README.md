# jort
[![PyPI version](https://badge.fury.io/py/jort.svg)](https://badge.fury.io/py/jort) 

Track, profile, and notify at custom checkpoints in your coding scripts

## Installation
```
pip install jort
```

## Usage
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

## Logging

`jort` automatically logs results by default. You can change the destination filename, as well as the level of verbosity: 0 - no logging, 1 - only elapsed times, 2 - start and stop times. Defaults are `logname='tracker.log'` and `verbose=2`.
```
import jort
from time import sleep

tr = jort.Tracker(logname='my_log.log', verbose=1)
```

## Function Decorators
`jort` also supports timing functions with decorators, via `Tracker.track`. Demonstrating on the first example:
```
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
```

The printed report appears as:
```
my_script | 11.0 s ± 0.0 s per iteration, n = 1
sleep_1s | 1.0 s ± 0.0 s per iteration, n = 10
```

## Future Directions

* Potential support for more complex profiling
