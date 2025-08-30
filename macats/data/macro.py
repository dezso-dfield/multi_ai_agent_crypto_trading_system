from datetime import datetime, timedelta
from typing import List, Dict

def toy_calendar() -> List[Dict]:
    """
    Returns a toy list of upcoming macro events.
    Extend later with EconDB, FRED, or paid macro feeds.
    """
    now = datetime.utcnow()
    return [
        {"when": (now + timedelta(hours=12)).isoformat(), "label": "US CPI"},
        {"when": (now + timedelta(days=2)).isoformat(), "label": "FOMC minutes"},
    ]