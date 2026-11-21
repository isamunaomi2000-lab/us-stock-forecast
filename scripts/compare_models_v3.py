import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from predict_stocks_v2 import analyze as analyze_v2
from predict_stocks_v3 import analyze as analyze_v3

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
WINDOW = 60
HORIZON = 5
OUTPUT = Path("data/model_comparison_v3")


def mean(values):
    return sum(values) / len(values)


def calculate_v1(closes, index):
    returns = [
        math.log(closes[j] / closes[j - 1])
        for j in range(index - WINDOW + 1, index + 1)
    ]
    return closes[index] * math.exp(
        mean(returns) * HORIZON
    )


def metrics(records):
    if not records:
        return None

    return {
        "count": len(records),
        "mean_absolute_error_pct": round(
            mean([r["error_pct"] for r in records]), 3
        ),
        "direction_accuracy_pct": round(
            100 * mean([r["direction_correct"] for r in records]),
            2
        )
    }


def evaluate(predicted, base, actual):
    return {
        "error_pct": abs(predicted - actual) / actual * 100,
        "direction_correct": int(
            (predicted > base and actual > base)
            or (predicted < base and actual < base)
            or (predicted == base and actual == base)
        )
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    results = []

    for ticker in TICKERS:
        path = Path("data/stocks") / f"{ticker}.csv"

        if not path.exists():
            print("Missing:", ticker)
            continue

        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

        closes = [float(r["close"]) for r in rows]

        if len(rows) < WINDOW + HORIZON + 1:
            print("Insufficient history:", ticker)
            continue

        if any(not math.isfinite(p) or p <= 0 for p in closes):
            print("Invalid prices:", ticker)
            continue

        ticker_records = []

        for i in range(WINDOW, len(rows) - HORIZON):
            # Only the most recent 61 rows through forecast date.
            historical_rows = rows[i - WINDOW:i + 1]
            base = closes[i]
            actual = closes[i + HORIZON]

            v1 = calculate_v1(closes, i)
            v2 = analyze_v2(historical_rows)
            v3 = analyze_v3(historical_rows)

            if v2 is None or v3 is None:
                continue

            predictions = {
                "V1": v1,
                "V2": float(v2["forecast_5d"]),
                "V3": float(v3["forecast_5d"])
            }

            for model, predicted in predictions.items():
                result = evaluate(predicted, base, actual)
                record = {
                    "ticker": ticker,
                    "model": model,
                    "forecast_date": rows[i]["date"],
                    "target_date": rows[i + HORIZON]["date"],
                    "predicted": round(predicted, 6),
                    "actual": actual,
                    **result
                }
                ticker_records.append(record)
                results.append(record)

        # Split by forecast date into earlier 80% and later 20%.
        dates = sorted(set(
            r["forecast_date"] for r in ticker_records
        ))
        split_index = int(len(dates) * 0.8)
        split_date = dates[split_index]

        summary[ticker] = {
            "split_date": split_date,
            "models": {}
        }

        for model in ["V1", "V2", "V3"]:
            model_records = [
                r for r in ticker_records
                if r["model"] == model
            ]

            earlier = [
                r for r in model_records
                if r["forecast_date"] < split_date
                and r["target_date"] < split_date
            ]
            later = [
                r for r in model_records
                if r["forecast_date"] >= split_date
            ]

            summary[ticker]["models"][model] = {
                "earlier_period": metrics(earlier),
                "later_period": metrics(later)
            }

        print(ticker, summary[ticker])

    report = {
        "updated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "historical_three_model_comparison",
        "horizon_trading_days": HORIZON,
        "by_ticker": summary,
        "notes": [
            "V1, V2, and V3 use the same forecast dates.",
            "Only information available on each forecast date is used.",
            "The 80/20 split is descriptive, not model training.",
            "V2 and V3 are experimental, with fixed parameters.",
            "The later period has already informed model development.",
            "Do not treat it as an untouched independent test.",
            "Adjusted historical prices may be revised.",
            "Overlapping five-day observations are dependent.",
            "Transaction costs are not included."
        ]
    }

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "model", "forecast_date", "target_date",
        "predicted", "actual", "error_pct", "direction_correct"
    ]

    with (OUTPUT / "results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print("Comparison completed:", len(results), "rows")


if __name__ == "__main__":
    main()
