#!/usr/bin/env python3
"""Jort command-line interface."""

import json
import os
import signal
import statistics

import click
import psutil

from . import config
from . import database
from . import datetime_utils
from . import detached
from . import reporting_callbacks
from . import track_cli
from ._version import __version__


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class LowerCaseFormatter(click.HelpFormatter):
    def write_usage(self, prog, args="", prefix="usage: "):
        super().write_usage(prog, args, prefix)


click.Context.formatter_class = LowerCaseFormatter


def _emit_result(payload, as_json, strict_notifications=False):
    if as_json:
        click.echo(json.dumps(payload, default=str))
    status = payload.get("status") if isinstance(payload, dict) else None
    if status in ("error", "terminated", "timeout"):
        raise click.exceptions.Exit(1)
    if strict_notifications:
        failed = [
            channel for channel, result in payload.get("notifications", {}).items()
            if result.get("status") == "failed"
        ]
        if failed:
            raise click.exceptions.Exit(2)


@click.group(
    context_settings=CONTEXT_SETTINGS,
    options_metavar="[-h] [-V]",
    subcommand_metavar="<command> [<args>]",
    cls=config.OrderedGroup,
)
@click.version_option(__version__, "-V", "--version")
def cli():
    """Track, benchmark, and notify about local jobs."""


@click.command(
    short_help="Track <job>, either a shell command or an existing PID",
    no_args_is_help=True,
    options_metavar="[<options>]",
    context_settings={"ignore_unknown_options": True},
)
@click.argument("job", nargs=-1, metavar="<job>")
@click.option("--pid", type=int, help="track an existing process explicitly")
@click.option("-t", "--text", is_flag=True, help="send SMS text at job exit")
@click.option("-e", "--email", is_flag=True, help="send email at job exit")
@click.option("-d", "--database", is_flag=True, help="store job details in database")
@click.option("-s", "--session", metavar="<session>", help="job session name for database")
@click.option("-u", "--unique", is_flag=True, help="skip a previously successful matching job")
@click.option("-o", "--output", is_flag=True, help="capture output for an email attachment")
@click.option("--max-output-bytes", type=click.IntRange(min=1), help="bound captured output size")
@click.option("--timeout", "timeout_seconds", type=click.FloatRange(min=0.001),
              help="terminate the job after this many seconds")
@click.option("--shell", is_flag=True, help="use shell execution for a new command")
@click.option("--argv", "argv_mode", is_flag=True,
              help="treat command arguments as an exact argv list")
@click.option("--cwd", type=click.Path(file_okay=False), help="working directory for a new command")
@click.option("--detach", is_flag=True, help="run the monitor in a durable background worker")
@click.option("--json", "as_json", is_flag=True, help="print a machine-readable result")
@click.option("--strict-notifications", is_flag=True,
              help="exit 2 when a requested notification cannot be sent")
@click.option("-q", "--quiet", is_flag=True, help="suppress live command output")
@click.option("-v", "--verbose", is_flag=True, help="print job payloads and details")
@click.pass_context
def track(ctx, job, pid, text, email, database, session, unique, output,
          max_output_bytes, timeout_seconds, shell, argv_mode, cwd, detach, as_json, strict_notifications,
          quiet, verbose):
    """Track <job>, either a shell command or an existing process."""
    explicit_pid = pid is not None
    implicit_pid = len(job) == 1 and job[0].isdigit()
    if explicit_pid or implicit_pid:
        process_id = pid if explicit_pid else int(job[0])
        if detach:
            result = detached.launch({
                "mode": "existing",
                "pid": process_id,
                "session_name": session,
                "send_text": text,
                "send_email": email,
            })
        else:
            if not as_json:
                click.echo(f"Tracking existing process PID at: {process_id}")
            existing_kwargs = dict(
                to_db=database,
                session_name=session,
                send_text=text,
                send_email=email,
                verbose=verbose,
            )
            if timeout_seconds is not None:
                existing_kwargs["timeout_seconds"] = timeout_seconds
            result = track_cli.track_existing(process_id, **existing_kwargs)
    else:
        joined_command = " ".join(job)
        command_input = list(job) if argv_mode else joined_command
        if argv_mode and shell:
            raise click.UsageError("--argv cannot be combined with --shell")
        if detach:
            result = detached.launch({
                "mode": "new",
                "command": command_input,
                "use_shell": shell,
                "store_stdout": output,
                "max_output_bytes": max_output_bytes,
                "timeout_seconds": timeout_seconds,
                "cwd": cwd,
                "session_name": session,
                "send_text": text,
                "send_email": email,
            })
        else:
            if not as_json and not quiet:
                click.echo(f"Tracking command `{joined_command}`")
            track_kwargs = dict(
                use_shell=shell,
                store_stdout=output,
                save_filename=None,
                to_db=database,
                session_name=session,
                unique=unique,
                send_text=text,
                send_email=email,
                verbose=verbose,
            )
            if cwd is not None:
                track_kwargs["cwd"] = cwd
            if max_output_bytes is not None:
                track_kwargs["max_output_bytes"] = max_output_bytes
            if timeout_seconds is not None:
                track_kwargs["timeout_seconds"] = timeout_seconds
            if quiet or as_json:
                track_kwargs["quiet"] = True
            result = track_cli.track_new(command_input, **track_kwargs)
    _emit_result(result, as_json, strict_notifications=strict_notifications)


@click.command()
@click.argument("job", nargs=-1, metavar="<job>")
@click.option("-r", "--repeat", type=click.IntRange(min=1), default=3, show_default=True)
@click.option("--warmup", type=click.IntRange(min=0), default=1, show_default=True)
@click.option("--session", default="benchmark", show_default=True)
@click.option("--baseline-session", help="compare against successful runs in this session")
@click.option("--shell", is_flag=True)
@click.option("--cwd", type=click.Path(file_okay=False))
@click.option("-e", "--email", is_flag=True)
@click.option("-t", "--text", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def benchmark(job, repeat, warmup, session, baseline_session, shell, cwd, email, text, as_json):
    """Run a command repeatedly and summarize timing statistics."""
    command = " ".join(job)
    if not command:
        raise click.UsageError("a command is required")
    baseline = []
    if baseline_session is not None:
        fingerprint = track_cli._command_metadata(command, shell, cwd=cwd)["command_hash"]
        baseline = database.runtimes(session=baseline_session, command_hash=fingerprint)
    for _ in range(warmup):
        track_cli.track_new(command, use_shell=shell, cwd=cwd, quiet=True)
    results = [
        track_cli.track_new(
            command,
            use_shell=shell,
            cwd=cwd,
            to_db=True,
            session_name=session,
            quiet=True,
        )
        for _ in range(repeat)
    ]
    runtimes = [result["runtime"] for result in results]
    summary = {
        "command": command,
        "session": session,
        "repeat": repeat,
        "warmup": warmup,
        "status": "success" if all(result["status"] == "success" for result in results) else "error",
        "mean_seconds": statistics.mean(runtimes),
        "median_seconds": statistics.median(runtimes),
        "p95_seconds": sorted(runtimes)[min(len(runtimes) - 1, max(0, int(len(runtimes) * 0.95)))],
        "stdev_seconds": statistics.stdev(runtimes) if len(runtimes) > 1 else 0.0,
        "job_ids": [result["job_id"] for result in results],
        "finished": datetime_utils.get_iso_date(),
    }
    if baseline:
        baseline_median = statistics.median(baseline)
        summary["baseline_session"] = baseline_session
        summary["baseline_median_seconds"] = baseline_median
        summary["delta_percent"] = ((summary["median_seconds"] - baseline_median) / baseline_median * 100
                                     if baseline_median else None)
    notification_payload = {
        "name": f"benchmark: {command}",
        "status": summary["status"],
        "runtime": summary["mean_seconds"],
        "date_modified": summary["finished"],
        "machine": config.socket.gethostname(),
        "stdout_fn": None,
        "error_message": None if summary["status"] == "success" else "one or more repetitions failed",
    }
    notifications = {}
    for callback in track_cli._notification_callbacks(
        send_email=email,
        send_text=text,
        include_print=not as_json,
    ):
        channel = getattr(callback, "channel", callback.__class__.__name__.lower())
        if channel == "print":
            callback.execute(notification_payload)
            continue
        try:
            notifications[channel] = {"status": "sent", "result": callback.execute(notification_payload)}
        except Exception as error:
            notifications[channel] = {"status": "failed", "error": str(error)}
    if notifications:
        summary["notifications"] = notifications
    if as_json:
        click.echo(json.dumps(summary, default=str))
    else:
        click.echo(json.dumps(summary, indent=2, default=str))
    if summary["status"] != "success":
        raise click.exceptions.Exit(1)


@click.command()
@click.option("--json", "as_json", is_flag=True)
def doctor(as_json):
    """Validate local storage and notification configuration without sending."""
    checks = {}
    try:
        config.init_internal_config()
        checks["config"] = "ok"
        checks["data_dir"] = config._get_data_dir()
        database.ensure_database()
        checks["database"] = "ok"
    except Exception as error:
        checks["storage"] = f"error: {error}"
    for name, callback_type in (("email", reporting_callbacks.EmailNotification),
                                ("text", reporting_callbacks.TextNotification)):
        try:
            callback_type(validate=True)
            checks[name] = "configured"
        except Exception as error:
            checks[name] = f"not configured: {error}"
    if as_json:
        click.echo(json.dumps(checks, default=str))
    else:
        for name, value in checks.items():
            click.echo(f"{name}: {value}")
    if any(str(value).startswith("error:") for value in checks.values()):
        raise click.exceptions.Exit(1)


@click.command()
@click.argument("job_id")
def cancel(job_id):
    """Request termination of a running or queued job."""
    payload = database.get_job(job_id)
    if payload is None:
        raise click.ClickException(f"No job found with id `{job_id}`")
    if payload.get("status") not in ("running", "queued"):
        click.echo(f"Job is already {payload.get('status')}")
        return
    pid = payload.get("pid")
    if not pid:
        raise click.ClickException("Job has no live process ID")
    try:
        process = psutil.Process(int(pid))
        if os.name == "posix" and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        if payload.get("status") == "queued":
            payload["status"] = "terminated"
            payload["error_message"] = "cancelled before detached worker started"
            payload["date_modified"] = datetime_utils.get_iso_date()
            database.save_job(payload)
        click.echo(f"Termination requested for {job_id} (PID {pid})")
    except (psutil.NoSuchProcess, ProcessLookupError):
        click.echo(f"Process for {job_id} has already exited")
    except psutil.AccessDenied as error:
        raise click.ClickException(str(error)) from error


@click.group()
def notify():
    """Test and retry notification delivery."""


def _callback_for_channel(channel, validate=True):
    if channel == "email":
        return reporting_callbacks.EmailNotification(validate=validate)
    if channel == "text":
        return reporting_callbacks.TextNotification(validate=validate)
    raise click.ClickException(f"Unknown notification channel: {channel}")


@notify.command("test")
@click.option("-e", "--email", is_flag=True)
@click.option("-t", "--text", is_flag=True)
def notify_test(email, text):
    """Send a real test notification for configured channels."""
    if not email and not text:
        raise click.UsageError("choose --email, --text, or both")
    payload = {
        "name": "jort notification test",
        "status": "success",
        "runtime": 0.0,
        "date_modified": datetime_utils.get_iso_date(),
        "machine": config.socket.gethostname(),
        "stdout_fn": None,
        "error_message": None,
    }
    for channel, enabled in (("email", email), ("text", text)):
        if enabled:
            callback = _callback_for_channel(channel)
            callback.execute(payload)
            click.echo(f"{channel}: sent")


@notify.command("retry")
@click.argument("job_id")
@click.option("-e", "--email", is_flag=True)
@click.option("-t", "--text", is_flag=True)
def notify_retry(job_id, email, text):
    """Retry failed or pending notifications for a completed job."""
    payload = database.get_job(job_id)
    if payload is None:
        raise click.ClickException(f"No job found with id `{job_id}`")
    channels = [channel for channel, enabled in (("email", email), ("text", text)) if enabled]
    if not channels:
        channels = payload.get("notification_channels", [])
    for channel in channels:
        callback = _callback_for_channel(channel, validate=False)
        try:
            result = callback.execute(payload)
            database.update_notification(job_id, channel, "sent")
            payload.setdefault("notifications", {})[channel] = {"status": "sent", "result": result}
            click.echo(f"{channel}: sent")
        except Exception as error:
            database.update_notification(job_id, channel, "failed", str(error))
            payload.setdefault("notifications", {})[channel] = {"status": "failed", "error": str(error)}
            click.echo(f"{channel}: failed: {error}", err=True)
    database.save_job(payload)


@notify.command("pending")
@click.option("--json", "as_json", is_flag=True)
def notify_pending(as_json):
    """List notification deliveries that are not marked sent."""
    pending = database.pending_notifications()
    if as_json:
        click.echo(json.dumps(pending, default=str))
    else:
        click.echo(json.dumps(pending, indent=2, default=str))


cli.add_command(config.init)
cli.add_command(config.config_group)
cli.add_command(track)
cli.add_command(benchmark)
cli.add_command(doctor)
cli.add_command(notify)
cli.add_command(database.inspect)
cli.add_command(database.status)
cli.add_command(database.logs)
cli.add_command(cancel)


if __name__ == "__main__":
    cli()
