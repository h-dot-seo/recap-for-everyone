"""Versioned query-time interpretation; never rewrites stored timestamps."""
from datetime import date
import re

RULE = 'recap.timestamp.v1'
DAY = 86_400_000_000
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
MIN_US = (date.min.toordinal() - EPOCH_ORDINAL) * DAY
END_US = (date.max.toordinal() + 1 - EPOCH_ORDINAL) * DAY
ISO = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(Z|[+-][0-9]{2}:[0-9]{2})')
EPOCH = re.compile(r'([0-9]{1,11})(?:\.([0-9]{1,9}))?')
DATE = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')


def parse_timestamp(value):
    """Return (integer UTC microseconds, kind), or (None, 'unparsed').

    Any 1..11 digit string is Unix seconds, even a date-looking value.
    Fractional seconds are truncated to six digits before offset arithmetic.
    No clocks, local zones, floating point or platform epoch conversion.
    """
    if not isinstance(value, str) or len(value) > 35:
        return None, 'unparsed'
    match = ISO.fullmatch(value)
    if match:
        year, month, day, hour, minute, second = map(int, match.groups()[:6])
        fraction, zone = match.groups()[6:]
        try:
            ordinal = date(year, month, day).toordinal()
        except ValueError:
            return None, 'unparsed'
        if hour > 23 or minute > 59 or second > 59:
            return None, 'unparsed'
        offset = 0
        if zone != 'Z':
            hours, minutes = int(zone[1:3]), int(zone[4:6])
            if hours > 23 or minutes > 59:
                return None, 'unparsed'
            offset = (hours * 60 + minutes) * (1 if zone[0] == '+' else -1)
        instant = ((ordinal - EPOCH_ORDINAL) * DAY +
                   (hour * 3600 + minute * 60 + second - offset * 60) * 1_000_000 +
                   int((fraction or '').ljust(6, '0')[:6]))
        if MIN_US <= instant < END_US:
            return instant, 'parsed_iso'
        return None, 'unparsed'
    match = EPOCH.fullmatch(value)
    if match:
        whole, fraction = match.groups()
        return int(whole) * 1_000_000 + int((fraction or '').ljust(6, '0')[:6]), 'parsed_epoch_seconds'
    return None, 'unparsed'


def utc_text(microseconds):
    if microseconds is None:
        return None
    days, remainder = divmod(microseconds, DAY)
    day = date.fromordinal(EPOCH_ORDINAL + days)
    seconds, fraction = divmod(remainder, 1_000_000)
    hour, seconds = divmod(seconds, 3600)
    minute, second = divmod(seconds, 60)
    return f'{day.year:04}-{day.month:02}-{day.day:02}T{hour:02}:{minute:02}:{second:02}.{fraction:06}Z'


def date_bound(value, *, end=False):
    if value is None:
        return None
    match = DATE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError('time bounds must be valid YYYY-MM-DD UTC dates')
    try:
        day = date(*map(int, match.groups()))
    except ValueError as error:
        raise ValueError('time bounds must be valid YYYY-MM-DD UTC dates') from error
    return (day.toordinal() - EPOCH_ORDINAL + int(end)) * DAY


def validate_options(order, from_date, until_date):
    if order is not None and order not in ('recent', 'oldest'):
        raise ValueError('order must be recent or oldest')
    lower, upper = date_bound(from_date), date_bound(until_date, end=True)
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError('from date must not be later than until date')
    return lower, upper
