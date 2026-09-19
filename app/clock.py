"""Time source for the application.

Never call ``datetime.now()`` directly in business logic - depend on ``get_now``
instead so tests can freeze and move time.  All datetimes are *naive UTC*.
"""
from datetime import datetime, timezone


def get_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
