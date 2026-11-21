import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
INPUT = Path("data/stocks")
OUTPUT = Path("data/predictions_v2")
OUTPUT.mkdir(parents=True, exist_ok=True)

HORIZON = 5


def average(values):
    return sum(values) / len(values)


def calculate_rsi(prices, period=14):
    changes = [
        prices[i] - prices[i - 1]
        for i in range(len(prices) - period, len(prices))
    ]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    avg_gain = average(gains)
    avg_loss = average(losses)

    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def analyze(rows):
    closes = [float(r["close"]) for r in rows]
    volumes = [float(r["volume"]) for r in rows]

    if len(closes) < 61 or any(p <= 0 for p in closes):
        return None

    price = closes[-1]
    sma20 = average(closes[-20:])
    sma50 = average(closes[-50:])
    rsi = calculate_rsi(closes)

    log_returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
    ]
    recent = log_returns[-60:]
    mean_return = average(recent)
    volatility = math.sqrt(
        average([(r - mean_return) ** 2 for r in recent])
    )

    avg_volume = average(volumes[-21:-1])
    volume_ratio = (
        volumes[-1] / avg_volume
        if avg_volume > 0 else 1.0
    )

    # Experimental directional signal, not a trained model.
    trend_signal = (
        (1 if price > sma20 else -1) +
        (1 if sma20 > sma50 else -1)
    ) / 2

    if rsi < 30:
        rsi_signal = 1.0
    elif rsi > 70:
        rsi_signal = -1.0
    else:
        rsi_signal = (50 - rsi) / 50

    # Volume amplifies the existing signal, not its direction.
    volume_factor = min(1.5, max(0.5, volume_ratio))

    signal = (
        0.7 * trend_signal +
        0.3 * rsi_signal
    ) * volume_factor

    # Conservative experimental adjustment to baseline drift.
    daily_adjustment = max(
        -0.005, min(0.005, signal * 0.002)
    )
    adjusted_return = mean_return + daily_adjustment

    forecast = price * math.exp(
        adjusted_return * HORIZON
    )

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
        "rsi14": round(rsi, 2),
        "volume_ratio": round(volume_ratio, 3),
        "daily_volatility_pct": round(volatility * 100, 3),
        "signal": round(signal, 4),
        "method": "experimental_trend_rsi_volume_v2"
    }


forecasts = []

for ticker in TICKERS:
    path = INPUT / f"{ticker}.csv"

    if not path.exists():
        print(f"Missing data: {ticker}")
        continue

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    result = analyze(rows)

    if result is None:
        print(f"Insufficient data: {ticker}")
        continue

    result["ticker"] = ticker
    result["as_of_date"] = rows[-1]["date"]
    forecasts.append(result)

    print(
        f"{ticker}: close={result['close']}, "
        f"forecast={result['forecast_5d']}, "
        f"RSI={result['rsi14']}"
    )


output = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "horizon_trading_days": HORIZON,
    "model": "experimental_v2",
    "validated": False,
    "forecasts": forecasts
}

(OUTPUT / "latest.json").write_text(
    json.dumps(output, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"Generated {len(forecasts)} experimental forecasts")
