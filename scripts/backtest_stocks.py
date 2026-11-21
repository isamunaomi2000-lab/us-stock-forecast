import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
WINDOW = 60
HORIZON = 5

INPUT = Path("data/stocks")
OUTPUT = Path("data/backtest")
OUTPUT.mkdir(parents=True, exist_ok=True)

summary = {}
all_results = []

for ticker in TICKERS:
    path = INPUT / f"{ticker}.csv"
    if not path.exists():
        print(f"Missing: {ticker}")
        continue

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    dates = [r["date"] for r in rows]
    prices = [float(r["close"]) for r in rows]

    if len(prices) < WINDOW + HORIZON + 1:
        print(f"Not enough data: {ticker}")
        continue

    log_returns = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i] > 0 and prices[i - 1] > 0
    ]

    if len(log_returns) != len(prices) - 1:
        print(f"Invalid prices: {ticker}")
        continue

    ticker_results = []

    for i in range(WINDOW, len(prices) - HORIZON):
        base = prices[i]
        actual = prices[i + HORIZON]

        recent = log_returns[i - WINDOW:i]
        mean_return = sum(recent) / WINDOW

        predicted = base * math.exp(
            mean_return * HORIZON
        )

        if base <= 0 or actual <= 0:
            continue

        error_pct = abs(predicted - actual) / actual * 100

        predicted_change = predicted - base
        actual_change = actual - base

        predicted_direction = (
            "up" if predicted_change > 0
            else "down" if predicted_change < 0
            else "flat"
        )
        actual_direction = (
            "up" if actual_change > 0
            else "down" if actual_change < 0
            else "flat"
        )

        result = {
            "ticker": ticker,
            "forecast_date": dates[i],
            "target_date": dates[i + HORIZON],
            "base_price": round(base, 4),
            "predicted_price": round(predicted, 4),
            "actual_price": round(actual, 4),
            "absolute_error_pct": round(error_pct, 3),
            "predicted_direction": predicted_direction,
            "actual_direction": actual_direction,
            "direction_correct": (
                predicted_direction == actual_direction
            )
        }

        ticker_results.append(result)
        all_results.append(result)

    if ticker_results:
        count = len(ticker_results)
        correct = sum(
            r["direction_correct"] for r in ticker_results
        )

        summary[ticker] = {
            "evaluated_predictions": count,
            "first_forecast_date": ticker_results[0]["forecast_date"],
            "last_forecast_date": ticker_results[-1]["forecast_date"],
            "mean_absolute_error_pct": round(
                sum(r["absolute_error_pct"] for r in ticker_results)
                / count, 3
            ),
            "direction_accuracy_pct": round(
                correct / count * 100, 2
            )
        }

        print(ticker, summary[ticker])


report = {
    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    "method": "historical_60d_log_return_baseline",
    "horizon_trading_days": HORIZON,
    "total_evaluated": len(all_results),
    "by_ticker": summary,
    "notes": [
        "Historical simulation, not saved real-time predictions.",
        "Uses only earlier observations for each forecast.",
        "Corporate-action adjustments may affect historical comparisons.",
        "Overlapping five-session forecasts are not independent."
    ]
}

(OUTPUT / "summary.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

fields = [
    "ticker", "forecast_date", "target_date",
    "base_price", "predicted_price", "actual_price",
    "absolute_error_pct", "predicted_direction",
    "actual_direction", "direction_correct"
]

with (OUTPUT / "results.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(all_results)

print(f"Completed: {len(all_results)} predictions")
