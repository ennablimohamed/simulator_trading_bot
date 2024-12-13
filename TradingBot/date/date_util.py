from datetime import datetime


def get_current_date():
    now_utc = datetime.utcnow()
    return now_utc.strftime("%d/%m/%YT%H:%M")


def compute_duration_until_now(date):

    current_time = datetime.utcnow()
    runtime = current_time - date
    days = runtime.days
    hours, remainder = divmod(runtime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m"
