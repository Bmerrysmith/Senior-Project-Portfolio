from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def previous_day_window(now=None):
    now = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    end = datetime.combine(now.date(), time.min, tzinfo=EASTERN)
    start = end - timedelta(days=1)
    return start, end
