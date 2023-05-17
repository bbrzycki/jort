import numpy as np


def format_reported_times(m, s=None, dec=1):
    format_str = ''
    if m >= 1.:
        format_str += f'{m:.{dec}f} s' 
        if s is not None:
            format_str += f' \u00B1 {s:.{dec}f} s'
    elif m >= 1e-3:
        format_str += f'{1e3 * m:.{dec}f} ms' 
        if s is not None:
            format_str += f' \u00B1 {1e3 * s:.{dec}f} ms'
    elif m >= 1e-6:
        format_str += f'{1e6 * m:.{dec}f} us' 
        if s is not None:
            format_str += f' \u00B1 {1e6 * s:.{dec}f} us'
    else:
        format_str += f'{1e9 * m:.{dec}f} ns' 
        if s is not None:
            format_str += f' \u00B1 {1e9 * s:.{dec}f} ns'
    return format_str


class Checkpoint(object):
    def __init__(self, name):
        """
        Create checkpoint to save times
        """
        self.name = name
        self.starts = []
        self.stops = []
        self.elapsed = []
        
    def _get_elapsed(self):
        self.elapsed = [y - x for (x, y) in zip(self.starts, self.stops)]
        
    def add_times(self, start, stop):
        self.starts.append(start)
        self.stops.append(stop)
        self.elapsed.append(stop - start)
    
    def report(self, dec=1):
        """
        Return formatted statistics.
        """
        elapsed_stats = format_reported_times(np.mean(self.elapsed), 
                                              np.std(self.elapsed), 
                                              dec=dec)
        return (
            f'{self.name} | '
            f'{elapsed_stats} per iteration, '
            f'n = {len(self.elapsed)}'
        )
        
    def __str__(self):
        return self.report(dec=1)
    