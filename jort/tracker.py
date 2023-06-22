import sys
import time
import sqlite3
import logging
import traceback
import functools
import shortuuid
import contextlib

from . import _config
from . import checkpoint
from . import datetime_utils
        

class Tracker(object):
    """
    A class to time sections of Python scripts by creating and closing timing
    checkpoints. 

    Parameters
    ----------
    log_name : str
        Filename for timing logs
    verbose : int, optional
        Options for verbosity. 0 for none, 1 for INFO, and 2 for DEBUG.
    to_db : bool, optional
        Save all checkpoint runtime details to database
    session_name : str, optional
        Name of job session, if saving jobs to database

    :ivar date_created: time of initialization
    :ivar machine: name of local machine
    :ivar checkpoints: dict of Checkpoints
    :ivar open_checkpoint_payloads: dict of job status payloads for open Checkpoints
    :ivar log_name: log filename
    :iver to_db: option to save all checkpoints to database
    :iver session_name: name of job session
    """
    def __init__(self, log_name="tracker.log", verbose=0, to_db=False, session_name=None):
        self.date_created = datetime_utils.get_iso_date()
        self.machine = _config.get_config_data().get("machine")
        self.checkpoints = {}
        self.open_checkpoint_payloads = {}

        # Manage session name, id; if session name is provided, get the id from db
        self.to_db = to_db
        self.session_name = session_name
        self.session_id = shortuuid.uuid()

        with contextlib.closing(sqlite3.connect(f"{_config.JORT_DIR}/jort.db")) as con:
            cur = con.cursor()
            if self.session_name is not None:
                sql = "SELECT session_id FROM sessions WHERE session_name == ?"
                res = cur.execute(sql, (self.session_name,))
                row = res.fetchone()
                if row is not None:
                    self.session_id = row[0]
            else:
                self.session_name = self.session_id
                if self.to_db:
                    sql = (
                        "INSERT INTO sessions VALUES(?, ?)"
                    )
                    cur.execute(sql, (self.session_id, self.session_name))
                    con.commit()

        self.log_name = log_name
        if verbose != 0:
            print(f"Starting session `{self.session_name}`")
            # if verbose == 1:
            #     level = logging.INFO
            # else:
            #     level = logging.DEBUG
            # file_handler = logging.FileHandler(filename=self.log_name, mode="w")
            # stdout_handler = logging.StreamHandler(sys.stdout)
            # handlers = [file_handler, stdout_handler]

            # logging.basicConfig(level=level,
            #                     format="%(asctime)s %(name)-15s %(levelname)-8s %(message)s",
            #                     handlers=handlers, 
            #                     force=True)
        
    def start(self, name=None, date_created=None):
        """
        Open checkpoint and start timer. Creates initial job status payload for use
        with notifications.

        Parameters
        ----------
        name : str
            Checkpoint name
        date_created : str, optional
            For an existing process, instead set this input as the creation date
        """
        if name is None:
            name = "Misc"
        name = str(name)
        if name in self.open_checkpoint_payloads:
            raise RuntimeError(f"Open checkpoint named {name} already exists")
        
        if date_created is not None:
            start = date_created
        else:
            start = datetime_utils.get_iso_date()
        now = datetime_utils.get_iso_date()

        self.open_checkpoint_payloads[name] = {
            "user_id": None,
            "job_id": shortuuid.uuid(),
            "session_id": self.session_id,
            "name": name,
            "long_name": name,
            "status": "running",
            "machine": self.machine,
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
        
    def stop(self, name=None, callbacks=[], to_db=False):
        """
        Close checkpoint and stop timer. Store start, stop, and elapsed times.
        Process job status payload and execute notification callbacks.

        If checkpoint name isn't supplied, get the most recent checkpoint (last
        in, first out; LIFO).

        Parameters
        ----------
        name : str, optional
            Checkpoint name
        callbacks : list, optional
            List of optional notification callbacks
        to_db : bool, optional
            Save checkpoint runtime details to database
        """
        if name is None:
            name = list(self.open_checkpoint_payloads.keys())[-1]
        elif name not in self.open_checkpoint_payloads:
            raise KeyError(f"No open checkpoint named {name}")

        payload = self.open_checkpoint_payloads.pop(name)
        if payload["status"] == "running":
            payload["status"] = "success"
        start = payload["date_created"]
        stop = datetime_utils._update_payload_times(payload)
        self.checkpoints[name].add_times(start, stop)

        logger = logging.getLogger(f"{name}.stop")
        logger.debug("Profiling block stopped.")
        formatted_runtime = checkpoint.format_reported_times(self.checkpoints[name].elapsed[-1])
        logger.info(f"Elapsed time: {formatted_runtime}")

        if self.to_db or to_db:
            with contextlib.closing(sqlite3.connect(f"{_config.JORT_DIR}/jort.db")) as con:
                cur = con.cursor()
                # Make sure session info is included in db
                sql = (
                    "INSERT OR IGNORE INTO sessions VALUES(?, ?)"
                )
                cur.execute(sql, (self.session_id, self.session_name))
                # Insert job into db
                sql = (
                    "INSERT INTO jobs VALUES("
                    "    :job_id,"
                    "    :session_id,"
                    "    :name,"
                    "    :status,"
                    "    :machine,"
                    "    :date_created,"
                    "    :date_modified,"
                    "    :runtime,"
                    "    :stdout_fn,"
                    "    :error_message"
                    ")"
                )
                cur.execute(sql, payload)
                job_id = cur.lastrowid
                con.commit()

        for callback in callbacks:
            callback.execute(payload=payload)
        
    def remove(self, name=None):
        """
        Option to remove checkpoint start instead of completing a profiling
        set, such as on catching an error.

        Parameters
        ----------
        name : str, optional
            Checkpoint name
        """
        if name is None:
            name = list(self.open_checkpoint_payloads.keys())[-1]
        
        if name in self.open_checkpoint_payloads:
            payload = self.open_checkpoint_payloads.pop(name)
            logger = logging.getLogger(f"{name}.remove")
            logger.debug("Profiling block removed.")
        
    def clear_open(self):
        """
        Clear all open checkpoints / open job status payloads.
        """
        self.open_checkpoint_payloads = {}

    def raise_error(self):
        """
        Update information payload with error details for the outermost checkpoint,
        to only be used within the except block during exception handling.
        """
        name = list(self.open_checkpoint_payloads.keys())[0]
        payload = self.open_checkpoint_payloads[name]
        payload["status"] = "error"
        payload["error_message"] = traceback.format_exc().strip().split('\n')[-1]
        raise

    def track(self, f=None, callbacks=[], to_db=False, report=False):
        """
        Function wrapper for tracker, to be used as a decorator. Creates a checkpoint
        with the input function's name. 

        Without parameters / evaluation, the decorator simply creates the checkpoint 
        and times the input function. With parameters, this method can execute 
        callbacks and print a report. 

        Parameters
        ----------
        f : func, optional
            Function to decorate
        callbacks : list, optional
            List of optional notification callbacks
        to_db : bool, optional
            Save checkpoint runtime details to database
        report : bool, optional
            Option to print tracker report at function completion
        """
        assert callable(f) or f is None
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                self.start(name=func.__qualname__)
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    payload = self.open_checkpoint_payloads[func.__qualname__]
                    payload["status"] = "error"
                    payload["error_message"] = traceback.format_exc().strip().split('\n')[-1]
                    raise
                finally:
                    self.stop(name=func.__qualname__, callbacks=callbacks, to_db=to_db)
                    if report:
                        self.report()
                return result
            return wrapper
        return decorator(f) if f else decorator
        
    def report(self, dec=1):
        """
        Print formatted runtime statistics for all checkpoints.

        Parameters
        ----------
        dec : int
            Decimal precision
        """
        for name in self.checkpoints:
            ckpt = self.checkpoints[name]
            print(ckpt.report(dec=dec))
            
            
def track(f=None, callbacks=[], to_db=False, report=True):
    """
    Independent function wrapper, to be used as a decorator, that creates a one-off
    tracker.
    
    Without parameters / evaluation, the decorator simply times the input function
    and prints a report by default. With parameters, this method can execute notification
    callbacks and control whether or not to print a report. 

    Parameters
    ----------
    f : func, optional
        Function to decorate
    callbacks : list, optional
        List of optional notification callbacks
    to_db : bool, optional
        Save checkpoint runtime details to database
    report : bool, optional
        Option to print tracker report at function completion
    """
    return Tracker(verbose=0).track(f=f, callbacks=callbacks, to_db=to_db, report=report)