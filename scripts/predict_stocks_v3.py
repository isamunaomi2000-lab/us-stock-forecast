import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
HORIZON = 5
MIN_HISTORY = 61

DATA_DIR = Path("data/stocks")
OUTPUT_DIR = Path("data/predictions_v3")


def mean(values):
    return sum(values) / len(values)


def clamp(value, low, high):
    return max(low, min(high, value))


def analyze(rows):
    if len(rows) < MIN_HISTORY:
        return None

    closes = [float(row["close"]) for row in rows]

    if not all(math.isfinite(p) and p > 0 for p in closes):
        return None

    price = closes[-1]
    sma20 = mean(closes[-20:])
    sma50 = mean(closes[-50:])

    returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
    ]

    recent60 = returns[-60:]
    recent20 = returns[-20:]

    drift60 = mean(recent60)
    drift20 = mean(recent20)

    volatility = math.sqrt(
        mean([(r - drift60) ** 2 for r in recent60])
    )

    # Compare moving averages and their separation.
    trend_gap = (sma20 / sma50) - 1.0
    price_gap = (price / sma20) - 1.0

    # Fixed experimental regime thresholds.
    if trend_gap > 0.02 and price_gap > 0:
        regime = "uptrend"
        # In an uptrend, use recent momentum.
        daily_drift = clamp(drift20, -0.01, 0.01)

    elif trend_gap < -0.02 and price_gap < 0:
        regime = "downtrend"
        # In a downtrend, use recent momentum.
        daily_drift = clamp(drift20, -0.01, 0.01)

    else:
        regime = "sideways"
        # In sideways markets, dampen baseline drift.
        daily_drift = clamp(drift60 * 0.25, -0.005, 0.005)

    forecast = price * math.exp(daily_drift * HORIZON)

    # Illustrative log-normal 90% range, not calibrated.
    sigma = volatility * math.sqrt(HORIZON)
    low = forecast * math.exp(-1.645 * sigma)
    high = forecast * math.exp(1.645 * sigma)

    return {
        "close": round(price, 4),
        "forecast_5d": round(forecast, 4),
        "range_low_5d": round(low, 4),
        "range_high_5d": round(high, 4),
        "sma20": round(sma20, 4),
        "sma50": round(sma50, 4),
        "trend_gap_pct": round(trend_gap * 100, 3),
        "daily_volatility_pct": round(volatility * 100, 3),
        "regime": regime,
        "method": "experimental_regime_v3"
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    forecasts = []

    for ticker in TICKERS:
        path = DATA_DIR / f"{ticker}.csv"

        if not path.exists():
            print(f"Missing data: {ticker}")
            continue

        with path.open(
            encoding="utf-8-sig", newline=""
        ) as file:
            rows = list(csv.DictReader(file))

        result = analyze(rows)

        if result is None:
            print(f"Insufficient data: {ticker}")
            continue

        result["ticker"] = ticker
        result["as_of_date"] = rows[-1]["date"]
        forecasts.append(result)

        print(
            f"{ticker}: regime={result['regime']}, "
            f"close={result['close']}, "
            f"forecast={result['forecast_5d']}"
        )

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "model": "experimental_regime_v3",
        "validated": False,
        "horizon_trading_days": HORIZON,
        "forecasts": forecasts,
        "notes": [
            "Experimental regime-based forecasting.",
            "Regime thresholds are fixed, not trained.",
            "Prediction ranges are not empirically calibrated.",
            "Not a trading recommendation."
        ]
    }

    output = OUTPUT_DIR / "latest.json"
    output.write_text(
        json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        encoding="utf-8"
    )

    print(f"Saved {len(forecasts)} forecasts to {output}")


if __name__ == "__main__":
    main()
