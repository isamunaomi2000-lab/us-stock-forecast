import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6
from compare_trading_v63 import simulate_filtered

OUTPUT = Path("data/nvda_volatility_thresholds")
THRESHOLDS = [
    ("V6", None),
    ("30%", 0.30),
    ("32.5%", 0.325),
    ("35%", 0.35),
    ("37.5%", 0.375),
    ("40%", 0.40),
    ("45%", 0.45),
]


def summarize(trades):
    count = len(trades)
    pnl = sum(t["pnl_usd"] for t in trades)
    wins = sum(t["pnl_usd"] > 0 for t in trades)

    return {
        "trades": count,
        "pnl_usd": round(pnl, 2),
        "win_rate_pct": (
            round(100 * wins / count, 2)
            if count else None
        )
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    prices = v6.load_prices("NVDA")
    start = max(200, int(len(prices) * 0.8))
    window = prices[start - 200:]

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "start_date": prices[start]["date"],
        "end_date": prices[-1]["date"],
        "thresholds": {},
        "notes": [
            "Exploratory sensitivity analysis.",
            "Original V6 simulator is reused.",
            "Entry indicators use prior completed sessions.",
            "Thresholds were chosen after reviewing outcomes.",
            "This is NOT independent holdout validation.",
            "Do not select a live strategy solely from results.",
            "Daily OHLC execution is approximate."
        ]
    }

    all_trades = []
    years = [
        str(year)
        for year in range(
            int(prices[start]["date"][:4]),
            int(prices[-1]["date"][:4]) + 1
        )
    ]

    for name, threshold in THRESHOLDS:
        result, trades, blocked = simulate_filtered(
            window, threshold
        )

        by_year = {
            year: summarize([
                t for t in trades
                if t["entry_date"].startswith(year)
            ])
            for year in years
        }

        before = [
            t for t in trades
            if t["entry_date"] < "2025-01-01"
        ]
        after = [
            t for t in trades
            if t["entry_date"] >= "2025-01-01"
        ]

        report["thresholds"][name] = {
            "threshold_pct": (
                None if threshold is None
                else round(threshold * 100, 2)
            ),
            "total_return_pct": result["total_return_pct"],
            "ending_capital_usd": result[
                "ending_capital_usd"
            ],
            "max_drawdown_pct": result[
                "max_daily_close_drawdown_pct"
            ],
            "trade_count": result["trade_count"],
            "win_rate_pct": result["win_rate_pct"],
            "blocked_signal_days": len(blocked),
            "before_2025": summarize(before),
            "from_2025": summarize(after),
            "by_entry_year": by_year
        }

        for trade in trades:
            all_trades.append({
                "threshold": name,
                **trade
            })

        print(
            name,
            "return:", result["total_return_pct"],
            "drawdown:",
            result["max_daily_close_drawdown_pct"],
            "trades:", result["trade_count"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "threshold", "entry_date", "exit_date",
                "pnl_usd", "reason"
            ]
        )
        writer.writeheader()
        writer.writerows(all_trades)


if __name__ == "__main__":
    main()
