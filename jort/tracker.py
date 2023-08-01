import os
import sys
import linecache
import time
import sqlite3
import logging
import traceback
import functools
import shortuuid
import contextlib
import socket
import inspect

from . import config
from . import block
from . import datetime_utils
from . import exceptions
        

def _get_linenumber():
        call_frame = inspect.getframeinfo(inspect.stack()[2][0])
        return call_frame.lineno


class Tracker(object):
    """
    A class to time sections of Python scripts by creating and closing timing
    blocks. 

    Parameters
    ----------
    session_name : str, optional
        Name of job session, if saving jobs to database
    log_name : str
        Filename for timing logs
    verbose : int, optional
        Options for verbosity. 0 for none, 1 for INFO, and 2 for DEBUG.
    to_db : bool, optional
        Save all block runtime details to database

    :ivar date_created: time of initialization
    :ivar machine: name of local machine
    :ivar blocks: dict of Blocks
    :ivar open_block_payloads: dict of job status payloads for open Blocks
    :ivar log_name: log filename
    :iver to_db: option to save all blocks to database
    :iver session_name: name of job session
    """
    def __init__(self, session_name=None, log_name="tracker.log", verbose=0, to_db=False):
        self.date_created = datetime_utils.get_iso_date()
        self.machine = socket.gethostname() #config._get_config_data().get("machine")
        self.blocks = {}
        self.open_block_payloads = {}

        # Manage session name, id; if session name is provided, get the id from db
        self.session_name = session_name
        self.session_id = shortuuid.uuid()
        self.session_configured = False
        self.to_db = to_db
        if self.to_db:
            self._configure_db_session()

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
        
    def _configure_db_session(self):
        """
        Manage session name and id. If session name is provided, get the id from database.
        """
        try:
            with contextlib.closing(sqlite3.connect(config._get_database_path())) as con:
                cur = con.cursor()
                if self.session_name is not None:
                    sql = "SELECT session_id FROM sessions WHERE session_name = ?"
                    res = cur.execute(sql, (self.session_name,))
                    row = res.fetchone()
                    if row is not None:
                        self.session_id = row[0]
                else:
                    self.session_name = self.session_id
                    sql = (
                        "INSERT INTO sessions VALUES(?, ?)"
                    )
                    cur.execute(sql, (self.session_id, self.session_name))
                    con.commit()
            self.session_configured = True
        except sqlite3.OperationalError as e:
            raise exceptions.JortException("Missing database - make sure to initialize with `jort.init()` or `jort init`") from e

    def checkpoint(self, name=None, callbacks=[], to_db=False):
        """
        A checkpoint opens a timing block that closes at the next checkpoint.
        Note that the last checkpoint needs to be closed with stop().
        """
        # First close any existing checkpoints
        for ckpt_name, payload in self.open_block_payloads.copy().items():
            if payload["is_checkpoint"]:
                self.stop(name=ckpt_name, callbacks=callbacks, to_db=to_db)
        
        if name is None:
            name = f"Checkpoint - line {_get_linenumber()}"
        
        self.start(name=name, is_checkpoint=True)

    def start(self, name=None, date_created=None, is_checkpoint=False):
        """
        Open block and start timer. Creates initial job status payload for use
        with notifications.

        Parameters
        ----------
        name : str
            Block name
        date_created : str, optional
            For an existing process, instead set this input as the creation date
        is_checkpoint : bool, optional
            Whether block start is a checkpoint (stops at next checkpoint)
        """
        if name is None:
            name = "Misc"
        name = str(name)
        if name in self.open_block_payloads:
            raise RuntimeError(f"Open block named {name} already exists")
        
        if date_created is not None:
            start = date_created
        else:
            start = datetime_utils.get_iso_date()
        now = datetime_utils.get_iso_date()

        self.open_block_payloads[name] = {
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
            "is_checkpoint": is_checkpoint,
        }
        if name not in self.blocks:
            self.blocks[name] = block.Block(name)
        logger = logging.getLogger(f"{name}.start")
        logger.debug("Profiling block started.")
        
    def stop(self, name=None, callbacks=[], to_db=False):
        """
        Close block and stop timer. Store start, stop, and elapsed times.
        Process job status payload and execute notification callbacks.

        If block name isn't supplied, get the most recent block (last
        in, first out; LIFO).

        Parameters
        ----------
        name : str, optional
            Block name
        callbacks : list, optional
            List of optional notification callbacks
        to_db : bool, optional
            Save block runtime details to database
        """
        if name is None:
            name = list(self.open_block_payloads.keys())[-1]
        elif name not in self.open_block_payloads:
            raise KeyError(f"No open block named {name}")

        payload = self.open_block_payloads.pop(name)
        if payload["status"] == "running":
            payload["status"] = "success"
        start = payload["date_created"]
        stop = datetime_utils._update_payload_times(payload)
        self.blocks[name].add_times(start, stop)

        logger = logging.getLogger(f"{name}.stop")
        logger.debug("Profiling block stopped.")
        formatted_runtime = block.format_reported_times(self.blocks[name].elapsed[-1])
        logger.info(f"Elapsed time: {formatted_runtime}")

        if self.to_db or to_db:
            if not self.session_configured:
                self._configure_db_session()
            try:
                with contextlib.closing(sqlite3.connect(config._get_database_path())) as con:
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
            except sqlite3.OperationalError as e:
                raise exceptions.JortException("Missing database - make sure to initialize with `jort.init()` or `jort init`") from e

        for callback in callbacks:
            callback.execute(payload=payload)
        
    def remove(self, name=None):
        """
        Option to remove block start instead of completing a profiling
        set, such as on catching an error.

        Parameters
        ----------
        name : str, optional
            Block name
        """
        if name is None:
            name = list(self.open_block_payloads.keys())[-1]
        
        if name in self.open_block_payloads:
            payload = self.open_block_payloads.pop(name)
            logger = logging.getLogger(f"{name}.remove")
            logger.debug("Profiling block removed.")
        
    def clear_open(self):
        """
        Clear all open blocks / open job status payloads.
        """
        self.open_block_payloads = {}

    def raise_error(self):
        """
        Update information payload with error details for the outermost block,
        to only be used within the except block during exception handling.
        """
        name = list(self.open_block_payloads.keys())[0]
        payload = self.open_block_payloads[name]
        payload["status"] = "error"
        payload["error_message"] = traceback.format_exc().strip().split('\n')[-1]
        raise

    def track(self, f=None, callbacks=[], to_db=False, report=False):
        """
        Function wrapper for tracker, to be used as a decorator. Creates a block
        with the input function's name. 

        Without parameters / evaluation, the decorator simply creates the block 
        and times the input function. With parameters, this method can execute 
        callbacks and print a report. 

        Parameters
        ----------
        f : func, optional
            Function to decorate
        callbacks : list, optional
            List of optional notification callbacks
        to_db : bool, optional
            Save block runtime details to database
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
                    payload = self.open_block_payloads[func.__qualname__]
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
        Print formatted runtime statistics for all blocks.

        Parameters
        ----------
        dec : int
            Decimal precision
        """
        print()
        print(f"Session: {self.session_name}")
        for name in self.blocks:
            block = self.blocks[name]
            print(block.report(dec=dec))
        print()

    def exec(self, code_string):
        """
        Code string can be a series of statements, separated by newlines.
        """
        lines = [line.strip() for line in code_string.strip().split('\n')]
        for line in lines:
            self.start(name=line)
            exec(line)
            self.stop()


    def auto_line_monitor(self):
        self.first_monitor_pass = True
        class SetTrace(object):
            def __init__(self_, func):
                self_.func = func

            def __enter__(self_):
                sys.setprofile(self_.func)
                return self_

            def __exit__(self_, ext_type, exc_value, traceback):
                try:
                    self.stop()
                except IndexError:
                    pass
                sys.setprofile(None)

        def monitor(frame, event, arg):
            if event == "line":
                if not self.first_monitor_pass:
                    try:
                        self.stop()
                    except IndexError:
                        pass
                else:
                    self.first_monitor_pass = False
                lineno = frame.f_lineno
                filename = frame.f_globals["__file__"]
                if (filename.endswith(".pyc") or
                    filename.endswith(".pyo")):
                    filename = filename[:-1]
                name = frame.f_globals["__name__"]
                line = linecache.getline(filename, lineno)
                if 'import' in line:
                    self.start(line.strip())
                print("%s:%s: %s" % (name, lineno, line.rstrip()))
            return monitor
        return SetTrace(monitor)

    
            
            
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
        Save block runtime details to database
    report : bool, optional
        Option to print tracker report at function completion
    """
    return Tracker(verbose=0).track(f=f, callbacks=callbacks, to_db=to_db, report=report)