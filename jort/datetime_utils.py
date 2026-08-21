from datetime import datetime, timezone
import time


def get_iso_date(timestamp=None):
    """
    Return start date in ISO 8601 format
    
    Parameters
    ----------
    timestamp : float, optional
        Unix time in seconds

    Returns
    -------
    iso_time : string
        ISO time (UTC)
    """
    if timestamp is not None:
        value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    else:
        value = datetime.now(timezone.utc)
    return value.isoformat(timespec="microseconds")

def get_runtime(iso_date1, iso_date2):
    """
    Return runtime in seconds between two dates in ISO format.

    Parameters
    ----------
    iso_date1 : string
        Start date in ISO 8601
    iso_date2 : string
        Stop date in ISO 8601

    Returns
    -------
    runtime : float
        Runtime in seconds
    """
    first = datetime.fromisoformat(iso_date1)
    second = datetime.fromisoformat(iso_date2)
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    if second.tzinfo is None:
        second = second.replace(tzinfo=timezone.utc)
    runtime = second - first
    return runtime.total_seconds()


def format_timespan(seconds):
    """Return a compact human-readable duration without third-party deps."""
    def number(value):
        return f"{value:.3f}".rstrip("0").rstrip(".")

    seconds = float(seconds)
    if seconds < 1e-6:
        return f"{number(seconds * 1e9)} nanoseconds"
    if seconds < 1e-3:
        return f"{number(seconds * 1e6)} microseconds"
    if seconds < 1:
        return f"{number(seconds * 1e3)} milliseconds"
    if seconds < 60:
        return f"{number(seconds)} seconds"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)} minutes, {number(remainder)} seconds"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)} hours, {int(minutes)} minutes"

def _update_payload_times(payload):
    """
    Modify payload dictionary with current time and time elapsed.

    Parameters
    ----------
    payload : dict
        Dictionary with job status details

    Returns
    -------
    date_now : string
        Current ISO date
    """
    date_now = get_iso_date()
    if payload.get("_monotonic_start") is not None:
        runtime = max(0.0, time.monotonic() - payload["_monotonic_start"])
    else:
        runtime = get_runtime(payload["date_created"], date_now)
    payload['runtime'] = runtime
    payload['date_modified'] = date_now
    return date_now
