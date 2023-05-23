import os
import sys
import time
import subprocess
import uuid
import psutil
from tqdm import tqdm
from pprint import pprint

from . import tracker
from . import datetime_utils
from . import config
from . import reporting_callbacks


def track_new(command,
              store_stdout=False,
              save_filename=None,
              send_sms=False,
              send_email=False,
              verbose=False,
              update_period=-1):
    """
    Track execution time and details of new command line process.

    If update_period is negative, doesn't do payload updates.
    """
    callbacks = [reporting_callbacks.PrintReport()]
    if send_sms:
        callbacks.append(reporting_callbacks.SMSNotification())
    if send_email:
        callbacks.append(reporting_callbacks.EmailNotification())

    # Key for storing stdout text to file
    job_id = str(uuid.uuid4())
    if save_filename or store_stdout:
        stdout_fn = f"{job_id}.txt"
        stdout_path = f"{config.JORT_DIR}/{stdout_fn}"
    else:
        stdout_fn = None

    tr = tracker.Tracker()
    tr.start(name=command)

    payload = tr.open_checkpoint_payloads[command]

    payload['job_id'] = job_id
    payload['stdout_fn'] = stdout_fn

    # ACTUALLY START SUBPROCESS
    my_env = os.environ.copy()
    my_env["PYTHONUNBUFFERED"] = "1"

    p = psutil.Popen(command.split(),
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
            datetime_utils.update_payload_times(payload)
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

    # if store_stdout:
    #     s3.meta.client.upload_file(
    #         stdout_path,
    #         aws_credentials["bucket_name"],
    #         "private/%s/%s" % (aws_credentials["identity_id"], stdout_fn)
    #     )
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
                   send_sms=False,
                   send_email=False,
                   verbose=False,
                   update_period=-1):
    """
    Track execution time and details of existing command line process.

    If update_period is negative, doesn't do payload updates.
    """
    callbacks = [reporting_callbacks.PrintReport()]
    if send_sms:
        callbacks.append(reporting_callbacks.SMSNotification())
    if send_email:
        callbacks.append(reporting_callbacks.EmailNotification())

    # Does not support stdout tracking
    stdout_fn = None

    # Create process based on PID and grab relevant information
    p = psutil.Process(pid)
    job_id = str(uuid.uuid4())
    command = " ".join(p.cmdline())

    tr = tracker.Tracker()
    tr.start(name=command, date_created=datetime_utils.get_iso_date(p.create_time()))
    payload = tr.open_checkpoint_payloads[command]

    if verbose:
        pprint(payload)

    temp_start = time.time()

    while p.is_running():
        if update_period > 0 and time.time() - temp_start >= update_period:
            payload["status"] = "running"
            datetime_utils.update_payload_times(payload)
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