from datetime import datetime
import dateutil.parser


def get_iso_date(timestamp=None):
    """Return start date in ISO 8601 format"""
    if timestamp:
        return datetime.utcfromtimestamp(timestamp).isoformat()
    else:
        return datetime.utcnow().isoformat()

def get_runtime(iso_date1, iso_date2):
    """
    Return runtime in seconds between two dates in ISO format.
    """
    runtime = (
        dateutil.parser.parse(iso_date2) - dateutil.parser.parse(iso_date1)
    )
    return runtime.total_seconds()

# def get_current_times(start_date):
#     """Return current date in ISO 8601 format, as well as runtime calculated
#     from the starting date"""
#     # Start time in ISO 8601
#     now_date = get_iso_date()
#     runtime_s = get_runtime(now_date, start_date)
#     hours, remainder = divmod(runtime_s, 3600)
#     minutes, seconds = divmod(remainder, 60)
#     formatted_runtime = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

#     return now_date, formatted_runtime, runtime_s


def update_payload_times(payload):
    """
    Modify payload dictionary with current times. Returns current date.
    """
    date_now = get_iso_date()
    runtime = get_runtime(payload["date_created"], date_now)
    payload['runtime'] = runtime
    payload['date_modified'] = date_now
    return date_now