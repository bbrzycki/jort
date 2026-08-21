"""Launch a durable background worker for long-running jobs."""

import json
import os
import subprocess
import sys
import tempfile

import shortuuid

from . import config
from . import database
from . import datetime_utils


def launch(spec):
    """Persist a worker specification and launch it in a new session."""
    database.ensure_database()
    job_id = spec.get("job_id") or shortuuid.uuid()
    spec = {**spec, "job_id": job_id}
    requests_dir = os.path.join(config._get_data_dir(), "requests")
    os.makedirs(requests_dir, mode=0o700, exist_ok=True)
    fd, spec_path = tempfile.mkstemp(prefix=f"{job_id}-", suffix=".json", dir=requests_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(spec, stream)
            stream.flush()
            os.fsync(stream.fileno())
        process = subprocess.Popen(
            [sys.executable, "-m", "jort.worker", "--spec", spec_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        try:
            os.unlink(spec_path)
        except FileNotFoundError:
            pass
        raise

    now = datetime_utils.get_iso_date()
    database.save_job({
        "job_id": job_id,
        "session_id": None,
        "name": spec.get("command") or f"PID {spec.get('pid')}",
        "status": "queued",
        "machine": None,
        "date_created": now,
        "date_modified": now,
        "runtime": 0.0,
        "stdout_fn": None,
        "error_message": None,
        "pid": process.pid,
        "metadata": {"worker_pid": process.pid, "detached": True},
        "notification_channels": [
            channel for channel, enabled in (
                ("email", spec.get("send_email", False)),
                ("text", spec.get("send_text", False)),
            ) if enabled
        ],
    })
    return {"job_id": job_id, "status": "queued", "worker_pid": process.pid}
