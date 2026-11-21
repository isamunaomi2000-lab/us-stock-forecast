import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from predict_stocks_v2 import analyze

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
WINDOW = 60
HORIZON = 5
OUTPUT = Path("data/model_comparison")
OUTPUT.mkdir(parents=True, exist_ok=True)


def calculate_v1(closes, i):
    recent = [
        math.log(closes[j] / closes[j - 1])
        for j in range(i - WINDOW + 1, i + 1)
    ]
    return closes[i] * math.exp(
        sum(recent) / WINDOW * HORIZON
    )


def metrics(items):
    if not items:
        return None
    return {
        "count": len(items),
        "mean_absolute_error_pct": round(
            sum(x["error_pct"] for x in items) / len(items), 3
        ),
        "direction_accuracy_pct": round(
            100 * sum(x["correct"] for x in items)
            / len(items), 2
        )
    }


summary = {}
all_results = []

for ticker in TICKERS:
    path = Path("data/stocks") / f"{ticker}.csv"
    if not path.exists():
        continue

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    closes = [float(r["close"]) for r in rows]

    if len(rows) < WINDOW + HORIZON + 1:
        continue

    if any(p <= 0 for p in closes):
        print(f"Invalid prices: {ticker}")
        continue

    ticker_results = []

    for i in range(WINDOW, len(rows) - HORIZON):
        base = closes[i]
        actual = closes[i + HORIZON]

        v1 = calculate_v1(closes, i)

        # Only data available through this historical date.
        v2_result = analyze(rows[:i + 1])
        if v2_result is None:
            continue
        v2 = float(v2_result["forecast_5d"])

        for model, predicted in [("V1", v1), ("V2", v2)]:
            result = {
                "ticker": ticker,
                "model": model,
                "forecast_date": rows[i]["date"],
                "target_date": rows[i + HORIZON]["date"],
                "error_pct": abs(predicted - actual) / actual * 100,
                "correct": (
                    (predicted > base and actual > base)
                    or (predicted < base and actual < base)
                    or (predicted == base and actual == base)
                )
            }
            ticker_results.append(result)
            all_results.append(result)

    # Chronological 80/20 split, using forecast dates.
    unique_dates = sorted({
        x["forecast_date"] for x in ticker_results
    })
    split = int(len(unique_dates) * 0.8)
    split_date = unique_dates[split] if split < len(unique_dates) else None

    summary[ticker] = {
        "split_date": split_date,
        "models": {}
    }

    for model in ["V1", "V2"]:
        items = [x for x in ticker_results if x["model"] == model]
        train = [
            x for x in items
            if split_date and x["forecast_date"] < split_date
            and x["target_date"] < split_date
        ]
        test = [
            x for x in items
            if split_date and x["forecast_date"] >= split_date
        ]
        summary[ticker]["models"][model] = {
            "earlier_period": metrics(train),
            "later_period": metrics(test)
        }

    print(ticker, summary[ticker])


report = {
    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    "horizon_trading_days": HORIZON,
    "method": "chronological_80_20_comparison",
    "by_ticker": summary,
    "notes": [
        "V2 parameters are fixed experimental settings.",
        "The 80/20 split is descriptive, not model training.",
        "No future observations are used for individual forecasts.",
        "Do not tune parameters on the later period and then claim independent validation.",
        "Historical adjusted prices may reflect later corporate actions.",
        "Overlapping five-session observations are dependent."
    ]
}

(OUTPUT / "summary.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

fields = [
    "ticker", "model", "forecast_date", "target_date",
    "error_pct", "correct"
]
with (OUTPUT / "results.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(all_results)

print("Comparison completed:", len(all_results), "rows")
