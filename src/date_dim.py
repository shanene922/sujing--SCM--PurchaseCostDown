from __future__ import annotations

from datetime import date

import pandas as pd


DEFAULT_START = date(2026, 1, 1)
DEFAULT_END = date(2026, 12, 31)



def build_date_dim(min_date: pd.Timestamp | None, max_date: pd.Timestamp | None) -> pd.DataFrame:
    start = DEFAULT_START if min_date is None or pd.isna(min_date) else pd.Timestamp(min_date).date()
    end = DEFAULT_END if max_date is None or pd.isna(max_date) else pd.Timestamp(max_date).date()

    if start > DEFAULT_START:
        start = DEFAULT_START
    if end < DEFAULT_END:
        end = DEFAULT_END

    date_range = pd.date_range(start=start, end=end, freq="D")
    date_dim = pd.DataFrame({"Date": date_range})
    iso = date_dim["Date"].dt.isocalendar()
    date_dim["Year"] = date_dim["Date"].dt.year
    date_dim["MonthNo"] = date_dim["Date"].dt.month
    date_dim["Month"] = date_dim["Date"].dt.strftime("%Y-%m")
    date_dim["Quarter"] = "Q" + date_dim["Date"].dt.quarter.astype(str)
    date_dim["Day"] = date_dim["Date"].dt.day
    date_dim["WeekdayNo"] = date_dim["Date"].dt.weekday + 1
    date_dim["Weekday"] = date_dim["Date"].dt.strftime("%a")
    date_dim["WeekNo"] = iso.week.astype(int)
    date_dim["WeekKey"] = date_dim["Year"].astype(str) + "-W" + date_dim["WeekNo"].astype(str).str.zfill(2)
    return date_dim
