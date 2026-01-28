from __future__ import annotations

import json
from datetime import datetime, timedelta, time, timezone

# Try to import pytz
try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    pytz = None
    PYTZ_AVAILABLE = False

# Always try to import zoneinfo as fallback (even if pytz is available)
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None


def _load_timezones():
    """
    Load Israel and Guatemala timezones.

    Prefer pytz (repo dependency) and fall back to zoneinfo if needed.
    Handles cases where pytz imports but timezone() calls fail.
    """
    israel_tz = None
    guatemala_tz = None

    # Try pytz first
    if PYTZ_AVAILABLE:
        try:
            israel_tz = pytz.timezone("Asia/Jerusalem")
            guatemala_tz = pytz.timezone("America/Guatemala")
            return israel_tz, guatemala_tz
        except Exception:
            # pytz imported but timezone() failed (corrupted data, wrong version, etc.)
            # Fall through to zoneinfo fallback
            pass

    # zoneinfo fallback
    if ZoneInfo is not None:
        try:
            israel_tz = ZoneInfo("Asia/Jerusalem")
            guatemala_tz = ZoneInfo("America/Guatemala")
            return israel_tz, guatemala_tz
        except Exception:
            # zoneinfo also failed, fall through to approximation
            pass

    # Both failed - return None, None which triggers approximation fallback
    return None, None


def _make_local_dt(tz, d, t_: time) -> datetime:
    """
    Create a timezone-aware datetime for the given timezone, date, and time.

    - For pytz timezones, use localize() correctly.
    - For zoneinfo timezones, use tzinfo=.
    """
    naive = datetime.combine(d, t_)
    if PYTZ_AVAILABLE and tz is not None and hasattr(tz, "localize"):
        # is_dst=None to surface ambiguous/non-existent times during DST transitions
        return tz.localize(naive, is_dst=None)
    return naive.replace(tzinfo=tz)


def _compute_service_window_utc(now_utc: datetime, israel_tz, guatemala_tz) -> tuple[datetime, datetime]:
    """
    Compute the service window in UTC for a given reference 'now_utc'.

    Window definition (daily):
      - Start: 11:00 Israel local time
      - End:   20:00 Guatemala local time

    We anchor the window to a single Israel "service day" (Israel local date), then derive the
    corresponding Guatemala date from that start instant to avoid date mismatches.
    """
    if israel_tz is None or guatemala_tz is None:
        # Fallback approximation:
        # Israel winter approx UTC+2 => 11:00 -> 09:00 UTC
        # Guatemala UTC-6 => 20:00 -> 02:00 UTC next day
        today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start_utc = today_utc + timedelta(hours=9)
        window_end_utc = today_utc + timedelta(days=1, hours=2)
        # If we're past window_end, move to next day
        if now_utc > window_end_utc:
            window_start_utc += timedelta(days=1)
            window_end_utc += timedelta(days=1)
        return window_start_utc, window_end_utc

    now_israel = now_utc.astimezone(israel_tz)
    israel_service_date = now_israel.date()

    window_start_israel = _make_local_dt(israel_tz, israel_service_date, time(11, 0))
    window_start_utc = window_start_israel.astimezone(timezone.utc)

    start_in_gt = window_start_utc.astimezone(guatemala_tz)
    guatemala_service_date = start_in_gt.date()
    window_end_guatemala = _make_local_dt(guatemala_tz, guatemala_service_date, time(20, 0))
    window_end_utc = window_end_guatemala.astimezone(timezone.utc)

    if window_end_utc <= window_start_utc:
        window_end_utc += timedelta(days=1)

    return window_start_utc, window_end_utc


def compute_call_availability_status(now_utc: datetime) -> dict:
    """
    Deterministic core logic behind check_call_availability().

    Returns a JSON-serializable dict with:
      - day (based on Israel local day, when available)
      - customer_service: "open" | "currently_closed"
      - service_opens/service_closes strings
      - window_start_utc/window_end_utc (for debugging/logging)
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    israel_tz, guatemala_tz = _load_timezones()

    day_name = now_utc.astimezone(israel_tz).strftime("%A") if israel_tz else now_utc.strftime("%A")
    day_lower = day_name.lower()

    if israel_tz:
        is_sunday_in_israel = now_utc.astimezone(israel_tz).weekday() == 6
    else:
        is_sunday_in_israel = now_utc.weekday() == 6

    if is_sunday_in_israel:
        if israel_tz:
            now_israel = now_utc.astimezone(israel_tz)
            days_until_monday = (7 - now_israel.weekday()) % 7
            days_until_monday = 7 if days_until_monday == 0 else days_until_monday
            next_monday_date = now_israel.date() + timedelta(days=days_until_monday)
            next_open_israel = _make_local_dt(israel_tz, next_monday_date, time(11, 0))
            next_open_utc = next_open_israel.astimezone(timezone.utc)
        else:
            next_open_utc = (now_utc + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

        hours_until_open = max(0, int((next_open_utc - now_utc).total_seconds() // 3600))
        return {
            "day": day_lower,
            "customer_service": "currently_closed",
            "service_opens": f"service will resume on {next_open_utc.strftime('%A, %B %d')} at {next_open_utc.strftime('%H:%M')} UTC, {hours_until_open} hours from now",
            "window_start_utc": None,
            "window_end_utc": None,
        }

    today_start_utc, today_end_utc = _compute_service_window_utc(now_utc, israel_tz, guatemala_tz)
    prev_start_utc, prev_end_utc = _compute_service_window_utc(now_utc - timedelta(days=1), israel_tz, guatemala_tz)

    if prev_start_utc <= now_utc <= prev_end_utc:
        window_start_utc, window_end_utc = prev_start_utc, prev_end_utc
    else:
        window_start_utc, window_end_utc = today_start_utc, today_end_utc
        if now_utc > window_end_utc:
            window_start_utc, window_end_utc = _compute_service_window_utc(now_utc + timedelta(days=1), israel_tz, guatemala_tz)

    if window_start_utc <= now_utc <= window_end_utc:
        hours_until_close = max(0, int((window_end_utc - now_utc).total_seconds() // 3600))
        return {
            "day": day_lower,
            "customer_service": "open",
            "service_closes": f"service will close in the next {hours_until_close} hours",
            "window_start_utc": window_start_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "window_end_utc": window_end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    hours_until_open = max(0, int((window_start_utc - now_utc).total_seconds() // 3600))
    return {
        "day": day_lower,
        "customer_service": "currently_closed",
        "service_opens": f"service will resume on {window_start_utc.strftime('%A, %B %d')} at {window_start_utc.strftime('%H:%M')} UTC, {hours_until_open} hours from now",
        "window_start_utc": window_start_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "window_end_utc": window_end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def compute_call_availability_json(now_utc: datetime) -> str:
    """Convenience wrapper for tool usage."""
    return json.dumps(compute_call_availability_status(now_utc))

