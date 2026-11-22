import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("data/trading_comparison_v63")
OUTPUT = Path("data/trading_validation_v63_timeline")
MODELS = ["V6", "V6.3-A", "V6.3-B"]
SPLIT_DATE = "2025-01-01"


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
        ),
        "average_pnl_usd": (
            round(pnl / count, 2) if count else None
        )
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with (SOURCE / "summary.json").open(
        encoding="utf-8"
    ) as f:
        comparison = json.load(f)

    with (SOURCE / "trades.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        trades = list(csv.DictReader(f))

    for trade in trades:
        trade["pnl_usd"] = float(trade["pnl_usd"])

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "split_date": SPLIT_DATE,
        "by_model": {},
        "notes": [
            "Retrospective analysis of existing V6.3 results.",
            "Trade PnL is assigned to entry year.",
            "Period PnL is not a separately compounded return.",
            "Trade-level PnL does not reconstruct daily drawdown.",
            "Thresholds were chosen after inspecting outcomes.",
            "The later period is NOT an untouched holdout.",
            "No independent out-of-sample validation."
        ]
    }

    years = sorted({
        t["entry_date"][:4] for t in trades
    })

    for model in MODELS:
        selected = [
            t for t in trades if t["model"] == model
        ]
        before = [
            t for t in selected
            if t["entry_date"] < SPLIT_DATE
        ]
        after = [
            t for t in selected
            if t["entry_date"] >= SPLIT_DATE
        ]

        report["by_model"][model] = {
            "full_period": comparison["models"][model],
            "before_2025": summarize(before),
            "from_2025": summarize(after),
            "by_entry_year": {
                year: summarize([
                    t for t in selected
                    if t["entry_date"].startswith(year)
                ])
                for year in years
            }
        }

    baseline = report["by_model"]["V6"]
    differences = {}

    for model in ("V6.3-A", "V6.3-B"):
        current = report["by_model"][model]
        differences[model] = {
            "before_2025_pnl_difference_usd": round(
                current["before_2025"]["pnl_usd"]
                - baseline["before_2025"]["pnl_usd"], 2
            ),
            "from_2025_pnl_difference_usd": round(
                current["from_2025"]["pnl_usd"]
                - baseline["from_2025"]["pnl_usd"], 2
            ),
            "full_period_return_difference_points": round(
                current["full_period"]["total_return_pct"]
                - baseline["full_period"]["total_return_pct"],
                2
            ),
            "full_period_drawdown_difference_points": round(
                current["full_period"][
                    "max_daily_close_drawdown_pct"
                ]
                - baseline["full_period"][
                    "max_daily_close_drawdown_pct"
                ],
                2
            )
        }

    report["differences_vs_v6"] = differences

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "by_model": {
            model: {
                "before_2025": data["before_2025"],
                "from_2025": data["from_2025"],
                "by_entry_year": data["by_entry_year"]
            }
            for model, data in report["by_model"].items()
        },
        "differences_vs_v6": differences
    }, indent=2))


if __name__ == "__main__":
    main()
