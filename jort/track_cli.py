"""Command and process tracking for Jort's CLI and Python API."""

import contextlib
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

import psutil
import shortuuid

from . import config
from . import database
from . import datetime_utils
from . import exceptions
from . import reporting_callbacks
from . import tracker


def _notification_callbacks(send_text=False, send_email=False, include_print=True):
    """Build independent, lazy-validating notification callbacks."""
    callbacks = [reporting_callbacks.PrintReport()] if include_print else []
    if send_email:
        callbacks.append(reporting_callbacks.EmailNotification())
    if send_text:
        callbacks.append(reporting_callbacks.TextNotification())
    return callbacks


def _git_sha(cwd):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _command_metadata(command, use_shell, cwd=None):
    effective_cwd = os.path.abspath(cwd or os.getcwd())
    if not os.path.isdir(effective_cwd):
        raise exceptions.JortException(f"Working directory does not exist: {effective_cwd}")
    if isinstance(command, (list, tuple)):
        if use_shell:
            raise exceptions.JortException("argv mode cannot be combined with shell execution")
        argv = [str(value) for value in command]
        display_command = shlex.join(argv)
    else:
        display_command = str(command)
        argv = [display_command] if use_shell else shlex.split(display_command)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"command": display_command, "argv": argv, "shell": use_shell,
             "cwd": effective_cwd},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "command": display_command,
        "cwd": effective_cwd,
        "argv": argv,
        "git_sha": _git_sha(effective_cwd),
        "command_hash": fingerprint,
        "metadata": {"shell": bool(use_shell)},
    }


def _set_process_result(payload, returncode):
    payload["exit_code"] = returncode
    if returncode is None:
        payload["status"] = "finished"
        payload["error_message"] = None
    elif returncode == 0:
        payload["status"] = "success"
        payload["error_message"] = None
    elif returncode < 0:
        payload["status"] = "terminated"
        payload["signal"] = -returncode
        payload["error_message"] = f"process terminated by signal {-returncode}"
    else:
        payload["status"] = "error"
        payload["error_message"] = f"process exited with code {returncode}"


def _terminate_process(process):
    try:
        if os.name == "posix" and os.getpgid(process.pid) == process.pid:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, psutil.NoSuchProcess):
        pass


def _capture_line(stream, line, output_limit, state):
    if stream is None:
        return
    if output_limit is None:
        stream.write(line)
        return
    encoded = line.encode("utf-8", errors="replace")
    remaining = max(0, output_limit - state["bytes"])
    if remaining:
        clipped = encoded[:remaining].decode("utf-8", errors="replace")
        stream.write(clipped)
        state["bytes"] += len(clipped.encode("utf-8", errors="replace"))
    if len(encoded) > remaining and not state["truncated"]:
        stream.write("\n[jort] output truncated at configured limit\n")
        state["truncated"] = True


def _process_metrics(process, peak_rss=0):
    metrics = {"peak_rss_bytes": peak_rss or None}
    try:
        cpu = process.cpu_times()
        metrics["cpu_user_seconds"] = cpu.user
        metrics["cpu_system_seconds"] = cpu.system
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return metrics


def _is_successful_duplicate(command_hash, session_id, command):
    database.ensure_database()
    with contextlib.closing(sqlite3.connect(config._get_database_path())) as connection:
        row = connection.execute(
            "SELECT status FROM jobs WHERE session_id = ? "
            "AND (command_hash = ? OR job_name = ?) "
            "ORDER BY date_created DESC LIMIT 1",
            (session_id, command_hash, command),
        ).fetchone()
    return row is not None and row[0] == "success"


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
              update_period=-1,
              cwd=None,
              max_output_bytes=None,
              quiet=False,
              job_id=None,
              timeout_seconds=None):
    """Run and track a new command, returning its completed payload.

    The original dictionary-based return value is preserved. New fields include
    ``exit_code``, ``signal``, ``cwd``, ``argv``, ``git_sha``, ``command_hash``,
    ``metrics``, and per-channel ``notifications``.
    """
    if not command or (isinstance(command, str) and not command.strip()):
        raise exceptions.JortException("A command is required")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise exceptions.JortException("timeout_seconds must be positive")
    metadata = _command_metadata(command, use_shell, cwd=cwd)
    command = metadata["command"]
    persist = to_db or unique or send_email or send_text
    callbacks = _notification_callbacks(send_text=send_text, send_email=send_email,
                                        include_print=not quiet)
    if save_filename or store_stdout:
        os.makedirs(config._get_data_dir(), mode=0o700, exist_ok=True)
        stdout_fn = f"{shortuuid.uuid()}.txt"
        stdout_path = os.path.join(config._get_data_dir(), stdout_fn)
    else:
        stdout_fn = None
        stdout_path = None

    tr = tracker.Tracker(to_db=persist, session_name=session_name)
    if unique and _is_successful_duplicate(
        metadata["command_hash"], tr.session_id, command
    ):
        payload = {
            "job_id": job_id or shortuuid.uuid(),
            "session_id": tr.session_id,
            "name": command,
            "status": "skipped",
            "machine": tr.machine,
            "date_created": datetime_utils.get_iso_date(),
            "date_modified": datetime_utils.get_iso_date(),
            "runtime": 0.0,
            "stdout_fn": None,
            "error_message": None,
            "cwd": metadata["cwd"],
            "argv": metadata["argv"],
            "git_sha": metadata["git_sha"],
            "command_hash": metadata["command_hash"],
            "metadata": metadata["metadata"],
            "notification_channels": [],
        }
        if persist:
            database.save_job(payload)
        return payload

    notification_channels = []
    if send_email:
        notification_channels.append("email")
    if send_text:
        notification_channels.append("text")
    tr.start(
        name=command,
        job_id=job_id,
        metadata={
            **metadata,
            "stdout_fn": stdout_fn,
            "notification_channels": notification_channels,
        },
    )
    payload = tr.open_block_payloads[command]
    payload["signal"] = None
    output_stream = None
    capture_state = {"bytes": 0, "truncated": False}
    metric_state = {"peak_rss": 0}
    metric_stop = threading.Event()
    metric_thread = None

    try:
        my_env = os.environ.copy()
        my_env["PYTHONUNBUFFERED"] = "1"
        argv = command if use_shell else metadata["argv"]
        process = psutil.Popen(
            argv,
            shell=use_shell,
            cwd=metadata["cwd"],
            env=my_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            start_new_session=True,
        )
        payload["pid"] = process.pid
        if not quiet:
            print(f"Subprocess PID: {process.pid}\n")

        def sample_metrics():
            while not metric_stop.is_set():
                try:
                    metric_state["peak_rss"] = max(
                        metric_state["peak_rss"], process.memory_info().rss
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return
                metric_stop.wait(0.1)

        metric_thread = threading.Thread(target=sample_metrics, daemon=True)
        metric_thread.start()

        if stdout_path is not None:
            output_stream = open(stdout_path, "w", encoding="utf-8", errors="replace")
            output_stream.write(f"{command}\n----\n")

        timed_out = threading.Event()
        timer = None
        if timeout_seconds is not None:
            timer = threading.Timer(
                timeout_seconds,
                lambda: (timed_out.set(), _terminate_process(process)),
            )
            timer.daemon = True
            timer.start()

        temp_start = time.monotonic()
        buffer = ""
        for line in process.stdout:
            try:
                metric_state["peak_rss"] = max(
                    metric_state["peak_rss"], process.memory_info().rss
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if update_period > 0 and time.monotonic() - temp_start >= update_period:
                payload["status"] = "running"
                datetime_utils._update_payload_times(payload)
                buffer = ""
                temp_start = time.monotonic()
                if verbose:
                    from pprint import pprint
                    pprint(payload)
            if not quiet:
                sys.stdout.write(line)
                sys.stdout.flush()
            if output_stream is not None:
                _capture_line(output_stream, line, max_output_bytes, capture_state)
            buffer += line

        if process.stdout is not None:
            process.stdout.close()
        process.wait()
        if timed_out.is_set():
            payload["status"] = "timeout"
            payload["error_message"] = f"process exceeded {timeout_seconds} seconds"
            payload["exit_code"] = process.returncode
        else:
            _set_process_result(payload, process.returncode)
        payload["metrics"] = _process_metrics(
            process, peak_rss=metric_state["peak_rss"]
        )
        payload["output_truncated"] = capture_state["truncated"]
    except (OSError, ValueError, psutil.Error) as error:
        payload["status"] = "error"
        payload["error_message"] = str(error)
        payload["exit_code"] = None
    finally:
        metric_stop.set()
        if metric_thread is not None:
            metric_thread.join(timeout=1)
        if "timer" in locals() and timer is not None:
            timer.cancel()
        if output_stream is not None:
            output_stream.close()

    payload = tr.stop(callbacks=callbacks)
    if save_filename and stdout_path is not None:
        shutil.move(stdout_path, save_filename)
        payload["stdout_fn"] = os.path.abspath(save_filename)
        if persist:
            database.save_job(payload)
    if verbose:
        from pprint import pprint
        pprint(payload)
    return payload


def track_existing(pid,
                   to_db=False,
                   session_name=None,
                   send_text=False,
                   send_email=False,
                   verbose=False,
                   update_period=-1,
                   job_id=None,
                   timeout_seconds=None):
    """Track an existing process, reporting unknown exit status explicitly."""
    callbacks = _notification_callbacks(send_text=send_text, send_email=send_email)
    try:
        process = psutil.Process(int(pid))
        command_line = process.cmdline()
        command = " ".join(command_line) or f"PID {pid}"
        create_time = process.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
        raise exceptions.JortException(f"Cannot inspect process {pid}: {error}") from error

    metadata = {
        "cwd": None,
        "argv": command_line,
        "git_sha": None,
        "command_hash": hashlib.sha256(command.encode()).hexdigest(),
        "metadata": {"existing_pid": int(pid), "exit_status_known": False},
        "stdout_fn": None,
        "notification_channels": [
            channel for channel, enabled in (("email", send_email), ("text", send_text))
            if enabled
        ],
    }
    persist = to_db or send_email or send_text
    tr = tracker.Tracker(to_db=persist, session_name=session_name)
    tr.start(
        name=command,
        date_created=datetime_utils.get_iso_date(create_time),
        job_id=job_id,
        metadata=metadata,
    )
    payload = tr.open_block_payloads[command]
    payload["pid"] = int(pid)
    payload["_monotonic_start"] = time.monotonic() - max(0.0, time.time() - create_time)
    started_at = time.monotonic()
    temp_start = started_at
    timed_out = False
    while True:
        try:
            # A child that has exited but has not yet been reaped is reported
            # by psutil as a zombie. It is no longer executing, so treating
            # it as running would make an attached monitor wait forever.
            if not process.is_running() or process.status() in (
                psutil.STATUS_ZOMBIE,
                psutil.STATUS_DEAD,
            ):
                break
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            break
        if update_period > 0 and time.monotonic() - temp_start >= update_period:
            payload["status"] = "running"
            datetime_utils._update_payload_times(payload)
            temp_start = time.monotonic()
            if verbose:
                from pprint import pprint
                pprint(payload)
        if timeout_seconds is not None and time.monotonic() - started_at >= timeout_seconds:
            _terminate_process(process)
            timed_out = True
            break
        time.sleep(0.5)

    returncode = getattr(process, "returncode", None)
    if timed_out:
        payload["status"] = "timeout"
        payload["error_message"] = f"process exceeded {timeout_seconds} seconds"
    elif returncode is not None:
        _set_process_result(payload, returncode)
        payload["metadata"]["exit_status_known"] = True
    else:
        payload["status"] = "finished"
        payload["error_message"] = None
    return tr.stop(callbacks=callbacks)
