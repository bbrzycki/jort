import numpy as np
from . import datetime_utils


class Checkpoint(object):
    """
    Checkpoint object to mark start, stop, and elapsed times.

    Start and stop times are in ISO format, while elapsed times are in seconds.

    Parameters
    ----------
    name : string
        Checkpoint name

    :ivar name: checkpoint name
    :ivar starts: list of start times
    :ivar stops: list of stop times
    :ivar elapsed: list of elapsed times
    """
    def __init__(self, name):
        self.name = name 
        self.starts = [] 
        self.stops = [] 
        self.elapsed = [] 
        
    def _get_elapsed(self):
        self.elapsed = [datetime_utils.get_runtime(t1, t2) 
                        for (t1, t2) in zip(self.starts, self.stops)]
        
    def add_times(self, start, stop):
        """
        Store start, stop, and elpased times to checkpoint.

        Parameters
        ----------
        start : string
            ISO date of start
        stop : string
            ISO date of stop
        """
        self.starts.append(start)
        self.stops.append(stop)
        self.elapsed.append(datetime_utils.get_runtime(start, stop))
    
    def report(self, dec=1):
        """
        Return formatted runtime statistics.

        Parameters
        ----------
        dec : int
            Decimal precision

        Returns
        -------
        format_str : string
            Runtime details
        """
        if len(self.elapsed) > 0:
            elapsed_stats = format_reported_times(np.mean(self.elapsed), 
                                                np.std(self.elapsed), 
                                                dec=dec)
            return (
                f"{self.name} | "
                f"{elapsed_stats} per iteration, "
                f"n = {len(self.elapsed)}"
            )
        else:
            return (
                f"{self.name} | "
                f"no complete iterations, "
                f"n = {len(self.elapsed)}"
            )
        
    def __str__(self):
        return self.report(dec=1)
    

def format_reported_times(m, s=None, dec=1):
    """
    Format runtime strings, automatically adjusting units if runtimes 
    are under a second. 

    Parameters
    ----------
    m : float
        Mean runtime
    s : float, optional
        Standard deviation runtime
    dec : int, optional
        Decimal precision

    Returns
    -------
    format_str : string
        Runtime as a string
    """
    format_str = ""
    if m >= 1.:
        format_str += f"{m:.{dec}f} s" 
        if s is not None:
            format_str += f" \u00B1 {s:.{dec}f} s"
    elif m >= 1e-3:
        format_str += f"{1e3 * m:.{dec}f} ms" 
        if s is not None:
            format_str += f" \u00B1 {1e3 * s:.{dec}f} ms"
    elif m >= 1e-6:
        format_str += f"{1e6 * m:.{dec}f} us" 
        if s is not None:
            format_str += f" \u00B1 {1e6 * s:.{dec}f} us"
    else:
        format_str += f"{1e9 * m:.{dec}f} ns" 
        if s is not None:
            format_str += f" \u00B1 {1e9 * s:.{dec}f} ns"
    return format_str