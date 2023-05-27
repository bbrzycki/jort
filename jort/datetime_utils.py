from datetime import datetime
import dateutil.parser


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
    if timestamp:
        return datetime.utcfromtimestamp(timestamp).isoformat()
    else:
        return datetime.utcnow().isoformat()

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
    runtime = (
        dateutil.parser.parse(iso_date2) - dateutil.parser.parse(iso_date1)
    )
    return runtime.total_seconds()

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
    runtime = get_runtime(payload["date_created"], date_now)
    payload['runtime'] = runtime
    payload['date_modified'] = date_now
    return date_now