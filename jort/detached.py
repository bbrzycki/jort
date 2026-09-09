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
    session_id, session_name = database.get_or_create_session(
        spec.get("session_name")
    )
    spec = {**spec, "job_id": job_id, "session_name": session_name}
    now = datetime_utils.get_iso_date()
    queued_payload = {
        "job_id": job_id,
        "session_id": session_id,
        "name": spec.get("command") or f"PID {spec.get('pid')}",
        "status": "queued",
        "machine": None,
        "date_created": now,
        "date_modified": now,
        "runtime": 0.0,
        "stdout_fn": None,
        "error_message": None,
        "pid": None,
        "metadata": {"detached": True},
        "notification_channels": [
            channel for channel, enabled in (
                ("email", spec.get("send_email", False)),
                ("text", spec.get("send_text", False)),
            ) if enabled
        ],
    }
    # The dashboard must see the queued job before a fast worker can begin.
    # This also prevents the parent from overwriting a worker's running state.
    database.save_job(queued_payload)
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
    except Exception as error:
        try:
            os.unlink(spec_path)
        except FileNotFoundError:
            pass
        queued_payload.update({
            "status": "error",
            "error_message": str(error),
            "date_modified": datetime_utils.get_iso_date(),
        })
        database.save_job(queued_payload)
        raise

    queued_payload["pid"] = process.pid
    queued_payload["metadata"] = {"worker_pid": process.pid, "detached": True}
    database.save_job(queued_payload)
    return {"job_id": job_id, "status": "queued", "worker_pid": process.pid}
