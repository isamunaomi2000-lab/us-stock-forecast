import csv
import json
import math
import statistics
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6

OUTPUT = Path("data/nvda_loss_analysis")
TEST_FRACTION = 0.20
WARMUP = 200


def load_spy():
    with Path("data/stocks/SPY.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    return (
        [r["date"] for r in rows],
        [float(r["close"]) for r in rows]
    )


def features(rows, i):
    # Only completed sessions before entry.
    past = rows[i - 200:i]
    closes = [r["close"] for r in past]
    volumes = [r["volume"] for r in past]

    if len(past) != 200 or min(closes) <= 0:
        return None

    avg_volume = statistics.mean(volumes[-21:-1])
    changes = [
        math.log(closes[j] / closes[j - 1])
        for j in range(180, 200)
    ]

    return {
        "rsi14": round(v6.rsi14(closes), 2),
        "volume_multiple": (
            round(volumes[-1] / avg_volume, 3)
            if avg_volume > 0 else None
        ),
        "momentum20_pct": round(
            100 * (closes[-1] / closes[-21] - 1), 2
        ),
        "volatility20_pct": round(
            100 * statistics.stdev(changes)
            * math.sqrt(252), 2
        ),
        "distance_sma20_pct": round(
            100 * (
                closes[-1] / statistics.mean(closes[-20:]) - 1
            ), 2
        )
    }


def spy_features(date, dates, closes):
    pos = bisect_left(dates, date)
    if pos < 201:
        return None

    past = closes[pos - 201:pos]
    returns = [
        math.log(past[j] / past[j - 1])
        for j in range(len(past) - 20, len(past))
    ]

    return {
        "spy_above_sma200": (
            past[-1] > statistics.mean(past[-200:])
        ),
        "spy_momentum20_pct": round(
            100 * (past[-1] / past[-21] - 1), 2
        ),
        "spy_volatility20_pct": round(
            100 * statistics.stdev(returns)
            * math.sqrt(252), 2
        )
    }


def stats(items):
    if not items:
        return {
            "count": 0,
            "total_pnl_usd": 0,
            "average_pnl_usd": None
        }
    total = sum(x["pnl_usd"] for x in items)
    return {
        "count": len(items),
        "total_pnl_usd": round(total, 2),
        "average_pnl_usd": round(total / len(items), 2)
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    prices = v6.load_prices("NVDA")
    start = max(
        int(len(prices) * (1 - TEST_FRACTION)),
        WARMUP
    )
    window = prices[start - WARMUP:]

    result, trades = v6.simulate(window)
    spy_dates, spy_closes = load_spy()

    date_index = {
        row["date"]: i for i, row in enumerate(window)
    }

    records = []
    for trade in trades:
        entry_date = trade["entry_date"]
        if entry_date[:4] not in ("2025", "2026"):
            continue

        i = date_index[entry_date]
        stock = features(window, i)
        market = spy_features(
            entry_date, spy_dates, spy_closes
        )

        if stock is None or market is None:
            raise ValueError(
                "Missing prior data: " + entry_date
            )

        records.append({
            **trade,
            **stock,
            **market,
            "outcome": (
                "win" if trade["pnl_usd"] > 0
                else "loss" if trade["pnl_usd"] < 0
                else "flat"
            )
        })

    losses = [r for r in records if r["pnl_usd"] < 0]
    wins = [r for r in records if r["pnl_usd"] > 0]

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "years": [2025, 2026],
        "v6_test_return_pct": result["total_return_pct"],
        "all_trades": stats(records),
        "winning_trades": stats(wins),
        "losing_trades": stats(losses),
        "loss_reasons": {},
        "trades": records,
        "notes": [
            "Original V6 execution, unchanged.",
            "Indicators use only completed prior sessions.",
            "SPY data is strictly prior to entry.",
            "Diagnostic study, not a live trading signal.",
            "Nine or fewer trades may be too few for inference.",
            "No independent holdout validation."
        ]
    }

    for reason in sorted({r["reason"] for r in losses}):
        report["loss_reasons"][reason] = stats([
            r for r in losses if r["reason"] == reason
        ])

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    fields = [
        "entry_date", "exit_date", "pnl_usd",
        "reason", "outcome", "rsi14",
        "volume_multiple", "momentum20_pct",
        "volatility20_pct", "distance_sma20_pct",
        "spy_above_sma200", "spy_momentum20_pct",
        "spy_volatility20_pct"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(json.dumps({
        "all_trades": report["all_trades"],
        "winning_trades": report["winning_trades"],
        "losing_trades": report["losing_trades"],
        "loss_reasons": report["loss_reasons"]
    }, indent=2))


if __name__ == "__main__":
    main()
