import csv
import json
from datetime import datetime, timezone
from pathlib import Path

STOCKS = Path("data/stocks")
HISTORY = Path("data/predictions/history")
OUTPUT = Path("data/evaluation")
OUTPUT.mkdir(parents=True, exist_ok=True)

HORIZON = 5


def load_stock_prices(ticker):
    path = STOCKS / f"{ticker}.csv"
    if not path.exists():
        return []

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    return [
        {
            "date": row["date"],
            "close": float(row["close"])
        }
        for row in rows
    ]


results = []
price_cache = {}

for history_file in sorted(HISTORY.glob("*.json")):
    with history_file.open(encoding="utf-8") as f:
        saved = json.load(f)

    for forecast in saved.get("forecasts", []):
        ticker = forecast["ticker"]
        base_date = forecast["as_of_date"]

        if ticker not in price_cache:
            price_cache[ticker] = load_stock_prices(ticker)

        prices = price_cache[ticker]
        dates = [row["date"] for row in prices]

        if base_date not in dates:
            continue

        start_index = dates.index(base_date)
        target_index = start_index + HORIZON

        # Wait until five subsequent trading sessions exist.
        if target_index >= len(prices):
            continue

        target = prices[target_index]
        actual_price = target["close"]

        base_price = float(forecast["close"])
        predicted_price = float(forecast["forecast_5d"])

        if actual_price <= 0 or base_price <= 0:
            continue

        error = predicted_price - actual_price
        absolute_error_pct = (
            abs(error) / actual_price * 100
        )

        predicted_change = predicted_price - base_price
        actual_change = actual_price - base_price

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

        direction_correct = (
            predicted_direction == actual_direction
        )

        results.append({
            "ticker": ticker,
            "forecast_date": base_date,
            "target_date": target["date"],
            "base_price": round(base_price, 4),
            "predicted_price": round(predicted_price, 4),
            "actual_price": round(actual_price, 4),
            "absolute_error_pct": round(
                absolute_error_pct, 3
            ),
            "predicted_direction": predicted_direction,
            "actual_direction": actual_direction,
            "direction_correct": direction_correct
        })


fields = [
    "ticker",
    "forecast_date",
    "target_date",
    "base_price",
    "predicted_price",
    "actual_price",
    "absolute_error_pct",
    "predicted_direction",
    "actual_direction",
    "direction_correct"
]

with (OUTPUT / "daily_results.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)


summary = {}

for ticker in sorted({r["ticker"] for r in results}):
    items = [r for r in results if r["ticker"] == ticker]
    count = len(items)

    summary[ticker] = {
        "evaluated_predictions": count,
        "mean_absolute_error_pct": round(
            sum(r["absolute_error_pct"] for r in items)
            / count, 3
        ),
        "direction_accuracy_pct": round(
            sum(r["direction_correct"] for r in items)
            / count * 100, 1
        )
    }


report = {
    "updated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "horizon_trading_days": HORIZON,
    "total_evaluated": len(results),
    "by_ticker": summary,
    "results": results
}

(OUTPUT / "summary.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(report, ensure_ascii=False, indent=2))
