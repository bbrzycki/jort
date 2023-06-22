import os
import sys
import time
import sqlite3
import contextlib
import shlex
import subprocess
import uuid
import psutil
import shortuuid
from tqdm import tqdm
from pprint import pprint

from . import tracker
from . import datetime_utils
from . import _config
from . import reporting_callbacks


def track_new(command,
              use_shell=False,
              store_stdout=False,
              save_filename=None,
              to_db=False,
              session_name=None,
              unique=False,
              send_text=False,
              send_email=False,
              verbose=False,
              update_period=-1):
    """
    Track execution time and details of new command line process.

    Parameters
    ----------
    command : str
        Command to execute, which is spawned as a subprocess
    use_shell : bool, optional
        Option to use shell execution for subprocess
    store_stdout : bool, optional
        Option to write command output to file
    save_filename : str, optional
        Filename to which to save command output
    to_db : bool, optional
        Save all checkpoints to database
    session_name : str, optional
        Name of job session, if saving jobs to database
    unique : bool, optional
        Whether to skip job, if already successfully run and stored in database
    send_text : bool, optional
        Option to send SMS notification on completion
    send_email : bool, optional
        Option to send e-mail notification on completion
    verbose : bool, optional
        Option to control how much information is printed in stdout
    update_period : int, optional
        Number of seconds between each payload update and stdout write. If 
        :code:`update_period=-1`, as default, the only update occurs on completion.
    """
    callbacks = [reporting_callbacks.PrintReport()]
    if send_text:
        callbacks.append(reporting_callbacks.TextNotification())
    if send_email:
        callbacks.append(reporting_callbacks.EmailNotification())

    # Key for storing stdout text to file
    if save_filename or store_stdout:
        stdout_fn = f"{shortuuid.uuid()}.txt"
        stdout_path = f"{_config.JORT_DIR}/{stdout_fn}"
    else:
        stdout_fn = None

    tr = tracker.Tracker(to_db=to_db, session_name=session_name)
    if unique:
        with contextlib.closing(sqlite3.connect(f"{_config.JORT_DIR}/jort.db")) as con:
            cur = con.cursor()
            sql = (
                "SELECT status FROM jobs WHERE session_id == ? AND job_name == ?"
            )
            res = cur.execute(sql, (tr.session_id, command))
            for row in res.fetchall():
                status = row[0]
                if status == "success":
                    print("Found matching job that completed successfully; skipping...")
                    con.close()
                    return

    tr.start(name=command)

    payload = tr.open_checkpoint_payloads[command]

    payload['stdout_fn'] = stdout_fn

    # ACTUALLY START SUBPROCESS
    my_env = os.environ.copy()
    my_env["PYTHONUNBUFFERED"] = "1"

    if use_shell:
        p = psutil.Popen(command,
                         shell=True,
                         env=my_env,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         bufsize=1,
                         universal_newlines=True)
    else:
        p = psutil.Popen(shlex.split(command),
                         shell=False,
                         env=my_env,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         bufsize=1,
                         universal_newlines=True)
    print(f"Subprocess PID: {p.pid}\n")

    # Create stdout file
    if verbose:
        pprint(payload)
    if save_filename or store_stdout:
        with open(stdout_path, "a+") as f:
            f.write(f"{command}\n")
            f.write(f"--\n")

    buffer = ""
    temp_start = time.time()
    for line in p.stdout:
        if update_period > 0 and time.time() - temp_start >= update_period:
            if verbose:
                print("Buffered! (Not sent)", [buffer])
            if save_filename or store_stdout:
                with open(stdout_path, "a+") as f:
                    f.write(buffer)

            payload['status'] = 'running'
            datetime_utils._update_payload_times(payload)
            if verbose:
                pprint(payload)

            buffer = ""
            temp_start = time.time()

        sys.stdout.write(line)
        buffer += line


    if verbose:
        print("Buffered!", [buffer])
    if save_filename or store_stdout:
        with open(stdout_path, "a+") as f:
            f.write(buffer)

    p.wait()

    if verbose:
        print(f"Exit code: {p.returncode}")

    if p.returncode == 0:
        payload["status"] = "success"
    else:
        payload["status"] = "error"
        payload["error_message"] = line
    tr.stop(callbacks=callbacks)
    # print("")
    # if payload["runtime"] < 10:
    #     sys.exit("Job exited in 10 seconds -- no need to track!")

    if verbose:
        pprint(payload)

    if save_filename or store_stdout:
        if save_filename:
            subprocess.call(["cp", stdout_path, save_filename])
        try:
            subprocess.call(["rm", stdout_path])
        except Exception as e:
            raise e


def track_existing(pid,
                   to_db=False,
                   session_name=None,
                   send_text=False,
                   send_email=False,
                   verbose=False,
                   update_period=-1):
    """
    Track execution time and details of existing command line process.

    Parameters
    ----------
    pid : int
        Process ID of existing process
    to_db : bool, optional
        Save all checkpoints to database
    session_name : str, optional
        Name of job session, if saving jobs to database
    send_text : bool, optional
        Option to send SMS notification on completion
    send_email : bool, optional
        Option to send e-mail notification on completion
    verbose : bool, optional
        Option to control how much information is printed in stdout
    update_period : int, optional
        Number of seconds between each payload update. If 
        :code:`update_period=-1`, as default, the only update occurs on completion.
    """
    callbacks = [reporting_callbacks.PrintReport()]
    if send_text:
        callbacks.append(reporting_callbacks.TextNotification())
    if send_email:
        callbacks.append(reporting_callbacks.EmailNotification())

    # Does not support stdout tracking
    stdout_fn = None

    # Create process based on PID and grab relevant information
    p = psutil.Process(pid)
    command = " ".join(p.cmdline())

    tr = tracker.Tracker(to_db=to_db, session_name=session_name)
    tr.start(name=command, date_created=datetime_utils.get_iso_date(p.create_time()))
    payload = tr.open_checkpoint_payloads[command]

    if verbose:
        pprint(payload)

    temp_start = time.time()

    while p.is_running():
        if update_period > 0 and time.time() - temp_start >= update_period:
            payload["status"] = "running"
            datetime_utils._update_payload_times(payload)
            if verbose:
                pprint(payload)

            temp_start = time.time()

    payload["status"] = "finished"
    tr.stop(callbacks=callbacks)

    # print("")
    # if runtime_s < 60:
    #     sys.exit("Job exited in less than a minute -- no need to track!")

    if verbose:
        pprint(payload)