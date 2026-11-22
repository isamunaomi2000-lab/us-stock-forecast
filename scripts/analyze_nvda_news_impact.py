import csv
import json
from bisect import bisect_right
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import simulate_trading_v6 as v6

NEWS = Path("data/news/nvda_events.csv")
OUTPUT = Path("data/nvda_news_impact")
NY = ZoneInfo("America/New_York")


def pct(a, b):
    return round(100 * (b / a - 1), 2)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    prices = v6.load_prices("NVDA")
    dates = [r["date"] for r in prices]

    with NEWS.open(
        encoding="utf-8-sig", newline=""
    ) as f:
        news = list(csv.DictReader(f))

    results = []

    for item in news:
        try:
            published = datetime.fromisoformat(
                item["published_at_utc"]
            )
            if published.tzinfo is None:
                continue
            published = published.astimezone(NY)
        except (ValueError, KeyError):
            continue

        local_date = published.date().isoformat()
        # Without intraday timestamps, treat same-day
        # releases conservatively as next-session events.
        index = bisect_right(dates, local_date)

        if index == 0 or index >= len(prices):
            continue

        prior_close = prices[index - 1]["close"]
        first_close = prices[index]["close"]

        result = {
            "published_at_utc":
                item["published_at_utc"],
            "headline": item["headline"],
            "source": item["source"],
            "url": item["url"],
            "event_date_ny": local_date,
            "first_session_date": dates[index],
            "first_session_change_pct":
                pct(prior_close, first_close),
            "five_session_change_pct": None,
        }

        if index + 4 < len(prices):
            result["five_session_change_pct"] = (
                pct(
                    prior_close,
                    prices[index + 4]["close"]
                )
            )

        results.append(result)

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "event_count": len(results),
        "events": results,
        "notes": [
            "Descriptive event study only.",
            "All events are mapped to the next",
            "trading session after the NY calendar date.",
            "Same-day releases are not assigned",
            "to the same trading session.",
            "Returns are not adjusted for SPY.",
            "Overlapping events share return windows.",
            "News association does not prove causality.",
            "No intraday price reaction is measured.",
            "Five-session result requires five",
            "available sessions including first.",
        ],
    }

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("Analyzed news events:", len(results))
    for row in results[-10:]:
        print(
            row["first_session_date"],
            row["first_session_change_pct"],
            row["headline"][:70]
        )


if __name__ == "__main__":
    main()
