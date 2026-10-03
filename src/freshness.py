"""
Freshness: parse each job's ORIGINAL posting date (from the ATS) and compute
how many days ago it was posted. Lets us flag 🔥 jobs posted in the last ~2 days
so you can apply before the crowd.

Different ATS report dates differently:
  Greenhouse -> updated_at: ISO 8601
  Ashby      -> publishedAt: ISO 8601 or epoch milliseconds
  Workday    -> postedOn:    "Posted Today" / "Posted 3 Days Ago"
  Lever      -> (none)       -> age unknown
"""
import re
from datetime import datetime, timezone


def _parse_iso(s):
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_workday_relative(s):
    s = s.lower()
    if "today" in s:
        return 0
    if "yesterday" in s:
        return 1
    m = re.search(r"(\d+)\+?\s*day", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\+?\s*month", s)
    if m:
        return int(m.group(1)) * 30
    return None


def age_in_days(posted_at):
    if not posted_at:
        return None
    s = str(posted_at).strip()

    # Workday relative text
    if "posted" in s.lower() or "day" in s.lower() or "today" in s.lower():
        d = _parse_workday_relative(s)
        if d is not None:
            return d

    # epoch milliseconds (Ashby sometimes)
    if s.isdigit():
        try:
            dt = datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt).days)
        except Exception:
            return None

    dt = _parse_iso(s)
    if dt:
        return max(0, (datetime.now(timezone.utc) - dt).days)
    return None


def tag_freshness(jobs, fresh_days=2):
    for j in jobs:
        age = age_in_days(j.get("posted_at"))
        j["age_days"] = age
        j["fresh"] = age is not None and age <= fresh_days
    return jobs
