import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6

OUTPUT = Path("data/trading_comparison_v63")
THRESHOLDS = {
    "V6": None,
    "V6.3-A": 0.40,
    "V6.3-B": 0.35,
}


def prior_volatility(rows, i):
    closes = [r["close"] for r in rows[i - 200:i]]
    if len(closes) < 200 or min(closes) <= 0:
        return None

    returns = [
        math.log(closes[j] / closes[j - 1])
        for j in range(len(closes) - 20, len(closes))
    ]
    return statistics.stdev(returns) * math.sqrt(252)


def simulate_filtered(rows, threshold):
    # Use the original V6 simulator without modifying it.
    # Replace only its signal function temporarily.
    original_signal = v6.signal_at
    blocked_dates = set()

    def filtered_signal(data, i):
        if not original_signal(data, i):
            return False

        if threshold is None:
            return True

        volatility = prior_volatility(data, i)
        if volatility is None:
            return False

        if volatility >= threshold:
            blocked_dates.add(data[i]["date"])
            return False

        return True

    try:
        v6.signal_at = filtered_signal
        result, trades = v6.simulate(rows)
    finally:
        v6.signal_at = original_signal

    return result, trades, blocked_dates


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
        "models": {},
        "notes": [
            "V6 simulator and execution assumptions unchanged.",
            "Only entry signals are filtered by volatility.",
            "Volatility uses completed prior sessions only.",
            "The 35% and 40% thresholds were selected after",
            "inspecting historical NVDA losses.",
            "This is an in-sample exploratory comparison.",
            "No independent holdout validation.",
            "Same-day OHLC fills are approximations.",
            "No taxes, FX costs or market impact."
        ]
    }

    all_trades = []
    model_trades = {}

    for model, threshold in THRESHOLDS.items():
        result, trades, blocked = simulate_filtered(
            window, threshold
        )
        model_trades[model] = trades

        report["models"][model] = {
            **result,
            "volatility_limit_pct": (
                None if threshold is None
                else round(threshold * 100, 2)
            ),
            "blocked_signal_days": len(blocked),
            "blocked_dates": sorted(blocked)
        }

        for trade in trades:
            all_trades.append({
                "model": model,
                **trade
            })

    baseline = model_trades["V6"]
    baseline_by_entry = {
        t["entry_date"]: t for t in baseline
    }

    for model in ("V6.3-A", "V6.3-B"):
        candidate_dates = {
            t["entry_date"] for t in model_trades[model]
        }

        skipped = [
            trade for date, trade in baseline_by_entry.items()
            if date not in candidate_dates
        ]

        report["models"][model][
            "baseline_trades_not_taken"
        ] = {
            "count": len(skipped),
            "baseline_pnl_usd": round(
                sum(t["pnl_usd"] for t in skipped), 2
            ),
            "details": skipped
        }

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
                "model", "entry_date", "exit_date",
                "pnl_usd", "reason"
            ]
        )
        writer.writeheader()
        writer.writerows(all_trades)

    for model, result in report["models"].items():
        print(
            model,
            "return:", result["total_return_pct"],
            "drawdown:",
            result["max_daily_close_drawdown_pct"],
            "trades:", result["trade_count"]
        )


if __name__ == "__main__":
    main()
