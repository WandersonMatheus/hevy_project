import pandas as pd


def week_start(timestamps: pd.Series) -> pd.Series:
    """Bucket ISO8601 timestamps into Monday-start week periods (as dates)."""
    dt = pd.to_datetime(timestamps, utc=True, errors="coerce")
    return dt.dt.tz_localize(None).dt.to_period("W-MON").apply(lambda p: p.start_time.date())
