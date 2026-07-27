"""Calendar, local-first: a directory of .ics files is the source of truth.

Works with anything that can export/import ICS (Outlook, Google, Proton).
Live CalDAV sync can arrive later as another backend behind the same tools.
"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event as IcsEvent

from manas.kernel.config import settings
from manas.kernel.errors import ManasError
from manas.kernel.registry import tools


def _caldir() -> Path:
    d = Path(settings.calendar_dir).expanduser() if settings.calendar_dir \
        else settings.home / "calendar"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tools.register("calendar_read")
class CalendarRead:
    """List events in a window (default: next 7 days) across all .ics files."""
    risk_level = "SAFE"

    async def __call__(self, days: int = 7) -> list[dict]:
        now = datetime.now().astimezone()
        horizon = now + timedelta(days=days)
        out = []
        for f in sorted(_caldir().glob("*.ics")):
            cal = Calendar.from_ical(f.read_text())
            for ev in cal.walk("VEVENT"):
                start = ev.decoded("dtstart")
                if isinstance(start, datetime) and start.tzinfo is None:
                    start = start.astimezone()
                if not isinstance(start, datetime):     # all-day date
                    start = datetime.combine(start, datetime.min.time()).astimezone()
                if now - timedelta(days=1) <= start <= horizon:
                    out.append({"file": f.name,
                                "start": start.isoformat(),
                                "summary": str(ev.get("summary", "")),
                                "location": str(ev.get("location", ""))})
        return sorted(out, key=lambda e: e["start"])


@tools.register("calendar_add")
class CalendarAdd:
    """Create an event as a new .ics file. Writes user data -> REVIEW."""
    risk_level = "REVIEW"

    async def __call__(self, summary: str, start_iso: str,
                       duration_min: int = 30, location: str = "") -> dict:
        try:
            start = datetime.fromisoformat(start_iso)
        except ValueError as e:
            raise ManasError(f"start_iso must be ISO datetime: {e}") from e
        if start.tzinfo is None:
            start = start.astimezone()
        start = start.astimezone(timezone.utc)     # ICS in UTC: instant, not label
        cal = Calendar()
        cal.add("prodid", "-//MANAS//EN"); cal.add("version", "2.0")
        ev = IcsEvent()
        ev.add("uid", uuid.uuid4().hex)
        ev.add("summary", summary)
        ev.add("dtstart", start)
        ev.add("dtend", start + timedelta(minutes=duration_min))
        if location:
            ev.add("location", location)
        cal.add_component(ev)
        path = _caldir() / f"{start:%Y%m%d-%H%M}-{uuid.uuid4().hex[:6]}.ics"
        path.write_bytes(cal.to_ical())
        return {"saved": str(path), "summary": summary, "start": start.isoformat()}
