"""Persistence and inspection helpers for Jort jobs."""

import contextlib
import json
import os
import sqlite3
import uuid

import click

from . import config
from . import datetime_utils


JOB_COLUMNS = (
    "job_id", "session_id", "job_name", "status", "machine",
    "date_created", "date_finished", "runtime", "stdout_fn",
    "error_message", "pid", "exit_code", "signal", "cwd", "argv_json",
    "git_sha", "metadata_json", "command_hash",
    "notification_channels_json", "notifications_json",
)


def _connect():
    """Open a configured database connection and ensure the schema exists."""
    connection = sqlite3.connect(config._get_database_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_database():
    config.init_internal_config()
    data_dir = config._get_data_dir()
    config.Path(data_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    config._initialize_db()


def _json(value):
    return json.dumps(value, sort_keys=True) if value is not None else None


def save_job(payload):
    """Insert or replace a completed/running job using named columns."""
    ensure_database()
    values = {
        "job_id": payload.get("job_id"),
        "session_id": payload.get("session_id"),
        "job_name": payload.get("name"),
        "status": payload.get("status"),
        "machine": payload.get("machine"),
        "date_created": payload.get("date_created"),
        "date_finished": payload.get("date_modified"),
        "runtime": payload.get("runtime"),
        "stdout_fn": payload.get("stdout_fn"),
        "error_message": payload.get("error_message"),
        "pid": payload.get("pid"),
        "exit_code": payload.get("exit_code"),
        "signal": payload.get("signal"),
        "cwd": payload.get("cwd"),
        "argv_json": _json(payload.get("argv")),
        "git_sha": payload.get("git_sha"),
        "metadata_json": _json(payload.get("metadata")),
        "command_hash": payload.get("command_hash"),
        "notification_channels_json": _json(payload.get("notification_channels", [])),
        "notifications_json": _json(payload.get("notifications", {})),
    }
    placeholders = ", ".join(f":{column}" for column in JOB_COLUMNS)
    columns = ", ".join(JOB_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}" for column in JOB_COLUMNS if column != "job_id"
    )
    with contextlib.closing(_connect()) as connection:
        connection.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(job_id) DO UPDATE SET {updates}",
            values,
        )
        connection.commit()


def _decode_job(row):
    if row is None:
        return None
    payload = dict(row)
    payload["name"] = payload.pop("job_name", None)
    payload["date_modified"] = payload.pop("date_finished", None)
    for column, target in (
        ("argv_json", "argv"),
        ("metadata_json", "metadata"),
        ("notification_channels_json", "notification_channels"),
        ("notifications_json", "notifications"),
    ):
        value = payload.pop(column, None)
        try:
            default = [] if target in ("argv", "notification_channels") else {}
            payload[target] = json.loads(value) if value else default
        except json.JSONDecodeError:
            payload[target] = [] if target in ("argv", "notification_channels") else {}
    return payload


def get_job(job_id):
    ensure_database()
    with contextlib.closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    return _decode_job(row)


def list_jobs(session=None, tail=None, full_details=False):
    ensure_database()
    if full_details:
        sql = "SELECT jobs.* FROM jobs"
        if session is not None:
            sql += " JOIN sessions ON jobs.session_id = sessions.session_id"
    else:
        sql = (
            "SELECT jobs.job_id, jobs.job_name, sessions.session_name, jobs.status, "
            "jobs.machine, jobs.date_created, jobs.date_finished, jobs.runtime, "
            "jobs.pid, jobs.exit_code, jobs.error_message "
            "FROM jobs JOIN sessions ON jobs.session_id = sessions.session_id"
        )
    params = []
    if session is not None:
        sql += " WHERE sessions.session_name = ?"
        params.append(session)
    sql += " ORDER BY jobs.date_created"

    with contextlib.closing(_connect()) as connection:
        rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
    if session is not None and not rows:
        raise ValueError(f"No jobs found with session `{session}`")
    if tail is not None:
        rows = rows[-tail:] if tail > 0 else []
    return rows


def print_jobs(session=None, tail=None, full_details=False):
    """Return saved jobs as a DataFrame when pandas is installed."""
    rows = list_jobs(session=session, tail=tail, full_details=full_details)
    try:
        import pandas as pd
    except ImportError:
        return rows
    return pd.DataFrame(rows)


def enqueue_notifications(payload):
    channels = payload.get("notification_channels", [])
    if not channels:
        return
    ensure_database()
    now = datetime_utils.get_iso_date()
    with contextlib.closing(_connect()) as connection:
        for channel in channels:
            connection.execute(
                "INSERT OR IGNORE INTO notifications "
                "(notification_id, job_id, channel, status, attempts, date_created, date_modified) "
                "VALUES (?, ?, ?, 'pending', 0, ?, ?)",
                (uuid.uuid4().hex, payload["job_id"], channel, now, now),
            )
        connection.commit()


def update_notification(job_id, channel, status, error_message=None):
    ensure_database()
    now = datetime_utils.get_iso_date()
    with contextlib.closing(_connect()) as connection:
        connection.execute(
            "UPDATE notifications SET status = ?, attempts = attempts + 1, "
            "error_message = ?, date_modified = ? WHERE job_id = ? AND channel = ?",
            (status, error_message, now, job_id, channel),
        )
        connection.commit()


def pending_notifications(job_id=None):
    ensure_database()
    sql = "SELECT * FROM notifications WHERE status != 'sent'"
    params = []
    if job_id is not None:
        sql += " AND job_id = ?"
        params.append(job_id)
    with contextlib.closing(_connect()) as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def runtimes(session=None, command_hash=None):
    """Return successful runtimes for simple benchmark comparison."""
    ensure_database()
    sql = "SELECT jobs.runtime FROM jobs"
    params = []
    if session is not None:
        sql += " JOIN sessions ON jobs.session_id = sessions.session_id"
    clauses = ["jobs.status = 'success'"]
    if session is not None:
        clauses.append("sessions.session_name = ?")
        params.append(session)
    if command_hash is not None:
        clauses.append("jobs.command_hash = ?")
        params.append(command_hash)
    sql += " WHERE " + " AND ".join(clauses)
    with contextlib.closing(_connect()) as connection:
        return [row[0] for row in connection.execute(sql, params).fetchall() if row[0] is not None]


@click.command(options_metavar='[<options>]')
@click.option('-s', '--session', type=str, help='filter by session name')
@click.option('-r', '--rows', type=int, help='number of rows to print')
@click.option('-f', '--full-details', is_flag=True, help='show all details, including ids')
@click.option('--json', 'as_json', is_flag=True, help='print machine-readable JSON')
def inspect(session, rows, full_details, as_json):
    """Get saved job details from the local database."""
    result = list_jobs(session=session, tail=rows, full_details=full_details)
    if as_json:
        click.echo(json.dumps(result, default=str))
    else:
        click.echo(print_jobs(session=session, tail=rows, full_details=full_details))


@click.command()
@click.argument('job_id')
@click.option('--json', 'as_json', is_flag=True, help='print machine-readable JSON')
def status(job_id, as_json):
    """Show one job by ID."""
    payload = get_job(job_id)
    if payload is None:
        raise click.ClickException(f"No job found with id `{job_id}`")
    if as_json:
        click.echo(json.dumps(payload, default=str))
    else:
        click.echo(json.dumps(payload, indent=2, default=str))


@click.command()
@click.argument('job_id')
def logs(job_id):
    """Print captured output for one job."""
    payload = get_job(job_id)
    if payload is None:
        raise click.ClickException(f"No job found with id `{job_id}`")
    filename = payload.get("stdout_fn")
    if not filename:
        raise click.ClickException("This job has no captured output")
    path = os.path.join(config._get_data_dir(), filename)
    try:
        with open(path, "r", errors="replace") as stream:
            click.echo(stream.read(), nl=False)
    except FileNotFoundError as error:
        raise click.ClickException(f"Captured output is missing: {path}") from error
