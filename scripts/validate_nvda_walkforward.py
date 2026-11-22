import json
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6
from compare_trading_v63 import simulate_filtered

OUTPUT = Path("data/nvda_walkforward")
THRESHOLDS = [0.30, 0.325, 0.35, 0.375, 0.40, 0.45]

# Each test year is evaluated only after the training years.
TEST_YEARS = [2023, 2024, 2025, 2026]


def simulate_period(prices, start_date, end_date, threshold):
    start = next(
        (i for i, r in enumerate(prices)
         if r["date"] >= start_date),
        len(prices)
    )
    end = next(
        (i for i, r in enumerate(prices)
         if r["date"] >= end_date),
        len(prices)
    )

    if start < 200 or end - start < 11:
        return None

    # Warm up indicators using preceding 200 sessions.
    window = prices[start - 200:end]
    result, trades, blocked = simulate_filtered(
        window, threshold
    )

    return {
        "return_pct": result["total_return_pct"],
        "max_drawdown_pct": result[
            "max_daily_close_drawdown_pct"
        ],
        "trades": result["trade_count"],
        "win_rate_pct": result["win_rate_pct"],
        "blocked_signal_days": len(blocked)
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prices = v6.load_prices("NVDA")

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ticker": "NVDA",
        "method": "expanding_window_annual_reselection",
        "training_start": "2021-01-01",
        "test_years": {},
        "notes": [
            "Thresholds were already explored using data",
            "through 2026; this is a retrospective replay.",
            "This is NOT an untouched out-of-sample test.",
            "Each year is simulated with independent",
            "initial capital and reset portfolio state.",
            "Training selects highest total return.",
            "No minimum trade count is imposed.",
            "Indicators use prior completed sessions.",
            "Daily OHLC execution remains approximate.",
            "No taxes, FX costs or market impact."
        ]
    }

    for year in TEST_YEARS:
        training = {}
        train_end = f"{year}-01-01"

        for threshold in THRESHOLDS:
            result = simulate_period(
                prices, "2021-01-01",
                train_end, threshold
            )
            if result is not None:
                training[str(threshold)] = result

        if not training:
            continue

        selected = max(
            training,
            key=lambda key: (
                training[key]["return_pct"],
                -training[key]["max_drawdown_pct"]
            )
        )
        threshold = float(selected)

        test = simulate_period(
            prices,
            f"{year}-01-01",
            f"{year + 1}-01-01",
            threshold
        )
        baseline = simulate_period(
            prices,
            f"{year}-01-01",
            f"{year + 1}-01-01",
            None
        )

        if test is None or baseline is None:
            continue

        report["test_years"][str(year)] = {
            "selected_threshold_pct": round(
                threshold * 100, 2
            ),
            "training": training[selected],
            "test": test,
            "baseline_v6": baseline,
            "test_return_difference_points": round(
                test["return_pct"]
                - baseline["return_pct"], 2
            )
        }

        print(
            year,
            "selected:", round(threshold * 100, 2),
            "test:", test["return_pct"],
            "V6:", baseline["return_pct"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
