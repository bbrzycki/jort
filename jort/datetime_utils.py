from datetime import datetime
import dateutil.parser


def get_start_date(timestamp=None):
    """Return start date in ISO 8601 format"""
    if timestamp:
        return datetime.utcfromtimestamp(timestamp).isoformat()
    else:
        return datetime.utcnow().isoformat()


def get_current_times(start_date):
    """Return current date in ISO 8601 format, as well as runtime calculated
    from the starting date"""
    # Start time in ISO 8601
    now_date = datetime.utcnow().isoformat()

    runtime = (
        dateutil.parser.parse(now_date) - dateutil.parser.parse(start_date)
    )

    runtime_s = runtime.total_seconds()
    hours, remainder = divmod(runtime_s, 3600)
    minutes, seconds = divmod(remainder, 60)
    formatted_runtime = ('{:02}:{:02}:{:02}'
                         .format(int(hours), int(minutes), int(seconds)))

    return now_date, formatted_runtime, runtime_s
