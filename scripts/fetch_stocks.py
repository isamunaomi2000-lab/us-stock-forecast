import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]

OUTPUT = Path("data/stocks")
OUTPUT.mkdir(parents=True, exist_ok=True)

summary = []

for ticker in TICKERS:
    print(f"Fetching all available history: {ticker}...")

    try:
        stock = yf.Ticker(ticker)
        history = stock.history(
            period="max",
            interval="1d",
            auto_adjust=True
        )

        if history.empty:
            print(f"No data: {ticker}")
            continue

        output_file = OUTPUT / f"{ticker}.csv"

        with output_file.open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            writer = csv.writer(f)
            writer.writerow([
                "date", "open", "high", "low",
                "close", "volume"
            ])

            for date, row in history.iterrows():
                writer.writerow([
                    date.strftime("%Y-%m-%d"),
                    round(float(row["Open"]), 4),
                    round(float(row["High"]), 4),
                    round(float(row["Low"]), 4),
                    round(float(row["Close"]), 4),
                    int(row["Volume"]),
                ])

        latest = history.iloc[-1]

        summary.append({
            "ticker": ticker,
            "date": history.index[-1].strftime("%Y-%m-%d"),
            "close": round(float(latest["Close"]), 4),
            "volume": int(latest["Volume"]),
            "rows": len(history),
            "first_date": history.index[0].strftime("%Y-%m-%d"),
        })

        print(
            f"Saved {ticker}: {len(history)} rows "
            f"from {history.index[0].date()}"
        )

    except Exception as error:
        print(f"Error {ticker}: {error}")

result = {
    "updated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "stocks": summary,
}

(OUTPUT / "latest.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(result, ensure_ascii=False, indent=2))
