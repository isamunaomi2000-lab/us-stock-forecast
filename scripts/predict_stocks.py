import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path("data/stocks")
OUTPUT = Path("data/predictions")
OUTPUT.mkdir(parents=True, exist_ok=True)

tickers = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
results = []

for ticker in tickers:
    path = INPUT / f"{ticker}.csv"
    if not path.exists():
        print(f"Missing data: {ticker}")
        continue

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    prices = [float(row["close"]) for row in rows]

    if len(prices) < 61 or any(p <= 0 for p in prices):
        print(f"Insufficient data: {ticker}")
        continue

    latest = prices[-1]
    latest_date = rows[-1]["date"]

    # Log returns reduce the effect of price scale.
    log_returns = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
    ]

    # Baseline model: average daily return over 60 sessions.
    recent = log_returns[-60:]
    mean_return = sum(recent) / len(recent)

    variance = sum(
        (r - mean_return) ** 2 for r in recent
    ) / len(recent)

    volatility = math.sqrt(variance)

    # Five trading sessions ahead.
    horizon = 5
    forecast = latest * math.exp(mean_return * horizon)

    # Illustrative statistical range, not a calibrated guarantee.
    sigma = volatility * math.sqrt(horizon)
    low = forecast * math.exp(-1.645 * sigma)
    high = forecast * math.exp(1.645 * sigma)

    # Normal-distribution approximation for up probability.
    if sigma > 0:
        z = mean_return * horizon / sigma
        probability_up = 0.5 * (
            1 + math.erf(z / math.sqrt(2))
        )
    else:
        probability_up = 0.5

    results.append({
        "ticker": ticker,
        "as_of_date": latest_date,
        "close": round(latest, 4),
        "forecast_5d": round(forecast, 4),
        "range_low_5d": round(low, 4),
        "range_high_5d": round(high, 4),
        "probability_up_5d": round(probability_up, 4),
        "method": "60d_log_return_baseline",
    })

output = {
    "generated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "horizon_trading_days": 5,
    "forecasts": results,
}

(OUTPUT / "latest.json").write_text(
    json.dumps(output, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(output, ensure_ascii=False, indent=2))
