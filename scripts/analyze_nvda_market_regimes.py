import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6
from compare_trading_v63 import (
    simulate_filtered,
    prior_volatility,
)
from analyze_market_v62 import load_spy, market_state

OUTPUT = Path("data/nvda_market_regimes")
THRESHOLD = 0.35


def stats(items):
    total = sum(t["pnl_usd"] for t in items)
    wins = sum(t["pnl_usd"] > 0 for t in items)
    return {
        "trades": len(items),
        "pnl_usd": round(total, 2),
        "win_rate_pct": (
            round(100 * wins / len(items), 2)
            if items else None
        ),
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    prices = v6.load_prices("NVDA")
    start = max(200, int(len(prices) * 0.8))
    window = prices[start - 200:]
    index = {
        row["date"]: i for i, row in enumerate(window)
    }

    baseline, v6_trades, _ = simulate_filtered(
        window, None
    )
    filtered, filtered_trades, blocked = (
        simulate_filtered(window, THRESHOLD)
    )

    spy_dates, spy_closes = load_spy()
    filtered_dates = {
        t["entry_date"] for t in filtered_trades
    }
    baseline_dates = {
        t["entry_date"] for t in v6_trades
    }

    records = []

    for model, trades in [
        ("V6", v6_trades),
        ("V6.3-B", filtered_trades),
    ]:
        for trade in trades:
            date = trade["entry_date"]
            i = index[date]
            state = market_state(
                date, spy_dates, spy_closes
            )
            volatility = prior_volatility(window, i)

            if state is None or volatility is None:
                raise ValueError(
                    "Missing historical data: " + date
                )

            if model == "V6":
                category = (
                    "common_entry"
                    if date in filtered_dates
                    else "baseline_only"
                )
            else:
                category = (
                    "common_entry"
                    if date in baseline_dates
                    else "filtered_only"
                )

            records.append({
                "model": model,
                "category": category,
                **trade,
                "nvda_volatility20_pct": round(
                    volatility * 100, 2
                ),
                **state,
            })

    conditions = [
        "above_sma200",
        "sma50_above_sma200",
        "momentum20_positive",
        "volatility20_high",
    ]

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "period_start": prices[start]["date"],
        "period_end": prices[-1]["date"],
        "threshold_pct": 35,
        "models": {
            "V6": baseline,
            "V6.3-B": filtered,
        },
        "groups": {},
        "baseline_only_by_outcome": {},
        "notes": [
            "Descriptive analysis, not a new strategy.",
            "No new entry conditions are introduced.",
            "SPY and NVDA features use prior sessions.",
            "Trade PnL is grouped by entry conditions.",
            "Common entry dates may have different PnL.",
            "Baseline-only does not prove causation.",
            "Trade differences may reflect portfolio state.",
            "Threshold was selected after past results.",
            "No independent holdout validation.",
            "Daily OHLC execution is approximate.",
        ],
    }

    for category in [
        "V6",
        "V6.3-B",
        "baseline_only",
        "filtered_only",
    ]:
        if category in ("V6", "V6.3-B"):
            subset = [
                r for r in records
                if r["model"] == category
            ]
        else:
            subset = [
                r for r in records
                if r["category"] == category
            ]

        groups = {"all": stats(subset)}
        for condition in conditions:
            groups[condition] = {
                str(value).lower(): stats([
                    r for r in subset
                    if r[condition] == value
                ])
                for value in (True, False)
            }

        report["groups"][category] = groups

    skipped = [
        r for r in records
        if r["model"] == "V6"
        and r["category"] == "baseline_only"
    ]

    for outcome, predicate in [
        ("wins", lambda p: p > 0),
        ("losses", lambda p: p < 0),
    ]:
        subset = [
            r for r in skipped
            if predicate(r["pnl_usd"])
        ]
        report["baseline_only_by_outcome"][
            outcome
        ] = {
            **stats(subset),
            "trades": [
                {
                    "entry_date": r["entry_date"],
                    "pnl_usd": r["pnl_usd"],
                    "nvda_volatility20_pct":
                        r["nvda_volatility20_pct"],
                    "spy_momentum20_pct":
                        r["spy_momentum20_pct"],
                    "spy_volatility20_pct":
                        r["spy_volatility20_pct"],
                }
                for r in subset
            ],
        }

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    fields = [
        "model", "category", "entry_date",
        "exit_date", "pnl_usd", "reason",
        "nvda_volatility20_pct", "above_sma200",
        "sma50_above_sma200",
        "momentum20_positive",
        "volatility20_high",
        "spy_momentum20_pct",
        "spy_volatility20_pct",
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(records)

    print(json.dumps({
        "groups": report["groups"],
        "baseline_only_by_outcome": {
            k: {
                "count": v["trades"]
                if isinstance(v["trades"], int)
                else len(v["trades"]),
                "pnl_usd": v["pnl_usd"],
            }
            for k, v in report[
                "baseline_only_by_outcome"
            ].items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
