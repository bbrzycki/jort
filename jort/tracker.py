import sys
import time
import logging
from functools import wraps

from . import checkpoint
from . import datetime_utils
        

class Tracker(object):
    def __init__(self, logname="tracker.log", verbose=0):
        """
        Create tracker object. Arguments give logging options; verbosity 0 for none, 
        1 for INFO, and 2 for DEBUG.
        """
        self.date_created = datetime_utils.get_iso_date()
        self.checkpoints = {}
        self.open_checkpoint_payloads = {}
        self.logname = logname
        if verbose != 0:
            if verbose == 1:
                level = logging.INFO
            else:
                level = logging.DEBUG
            file_handler = logging.FileHandler(filename=self.logname, mode="w")
            stdout_handler = logging.StreamHandler(sys.stdout)
            handlers = [file_handler, stdout_handler]

            logging.basicConfig(level=level,
                                format="%(asctime)s %(name)-15s %(levelname)-8s %(message)s",
                                handlers=handlers, 
                                force=True)
        
    def start(self, name=None, date_created=None):
        if name == None:
            name = "Misc"
        if name in self.open_checkpoint_payloads:
            raise RuntimeError(f"Open checkpoint named {name} already exists")
        
        if date_created is not None:
            start = date_created
        else:
            start = datetime_utils.get_iso_date()
        now = datetime_utils.get_iso_date()

        self.open_checkpoint_payloads[name] = {
            "user_id": None,
            "job_id": None,
            "short_name": name,
            "long_name": name,
            "status": "running",
            "machine": None,
            "date_created": start,
            "date_modified": now,
            "runtime": datetime_utils.get_runtime(start, now),
            "stdout_fn": None,
            "unread": True,
            "error_message": None,
        }

        if name not in self.checkpoints:
            self.checkpoints[name] = checkpoint.Checkpoint(name)
        logger = logging.getLogger(f"{name}.start")
        logger.debug("Profiling block started.")
        
    def stop(self, name=None, callbacks=[]):
        if name == None:
            name = list(self.open_checkpoint_payloads.keys())[-1]
        elif name not in self.open_checkpoint_payloads:
            raise KeyError(f"No open checkpoint named {name}")

        payload = self.open_checkpoint_payloads.pop(name)
        if payload["status"] == "running":
            payload["status"] = "success"
        start = payload["date_created"]
        stop = datetime_utils.update_payload_times(payload)
        self.checkpoints[name].add_times(start, stop)

        logger = logging.getLogger(f"{name}.stop")
        logger.debug("Profiling block stopped.")
        formatted_runtime = checkpoint.format_reported_times(self.checkpoints[name].elapsed[-1])
        logger.info(f"Elapsed time: {formatted_runtime}")

        for callback in callbacks:
            callback.execute(payload=payload)
        
    def remove(self, name=None):
        """
        Option to remove checkpoint start instead of completing a profiling
        set, for example on catching an error.
        """
        if name == None:
            name = list(self.open_checkpoint_payloads.keys())[-1]
        
        if name in self.open_checkpoint_payloads:
            payload = self.open_checkpoint_payloads.pop(name)
            logger = logging.getLogger(f"{name}.remove")
            logger.debug("Profiling block removed.")
        
    def clear_open(self):
        self.open_checkpoint_payloads = {}
        
    def time_func(self, f, report=False):
        """
        Function wrapper for tracker.
        """
        @wraps(f)
        def wrapper(*args, **kwargs):
            self.start(name=f.__qualname__)
            result = f(*args, **kwargs)
            self.stop(name=f.__qualname__)
            if report:
                self.report()
            return result
        return wrapper
        
    def report(self, dec=1):
        for name in self.checkpoints:
            ckpt = self.checkpoints[name]
            print(ckpt.report(dec=dec))
            
            
def time_func(f):
    """
    Independent function wrapper. Creates a one-off tracker and reports time.
    """
    return Tracker(verbose=0).time_func(f, report=True)
    # @wraps(f)
    # def wrapper(*args, **kwargs):
    #     tr.start(name=f.__qualname__)
    #     result = f(*args, **kwargs)
    #     tr.stop(name=f.__qualname__)
    #     tr.report()
    #     return result
    # return wrapper