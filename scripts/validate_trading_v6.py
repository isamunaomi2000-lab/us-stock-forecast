import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from simulate_trading_v5 import simulate as simulate_v5
from simulate_trading_v6 import simulate as simulate_v6

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
OUTPUT = Path("data/trading_validation_v6")


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        for key in ("open", "high", "low", "close", "volume"):
            row[key] = float(row[key])

    return rows


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "last_20_percent_v5_v6",
        "by_ticker": {},
        "notes": [
            "Retrospective comparison only.",
            "Not an independent unseen-data test.",
            "Same comparison dates and capital.",
            "Same stop, target, fees and allocation.",
            "Signals use completed previous sessions.",
            "Daily OHLC approximates execution.",
            "No taxes, FX costs or market impact."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        prices = load_prices(ticker)
        n = len(prices)

        if n < 250:
            report["by_ticker"][ticker] = {
                "status": "insufficient_history",
                "price_rows": n
            }
            print(ticker, "insufficient history")
            continue

        # Use the final 20% of the available history.
        # Keep 200 earlier sessions for indicators.
        start = max(200, int(n * 0.8))

        # Both models receive exactly the same rows.
        # Both first evaluate entries at window index 200.
        window = prices[start - 200:]

        v5_result = simulate_v5(window)
        v5_trades = v5_result.pop("trades", [])

        v6_result, v6_trades = simulate_v6(window)

        report["by_ticker"][ticker] = {
            "start_date": prices[start]["date"],
            "end_date": prices[-1]["date"],
            "V5": v5_result,
            "V6": v6_result
        }

        for model, trades in (
            ("V5", v5_trades),
            ("V6", v6_trades)
        ):
            for trade in trades:
                all_trades.append({
                    "ticker": ticker,
                    "model": model,
                    "entry_date": trade["entry_date"],
                    "exit_date": trade["exit_date"],
                    "pnl_usd": trade["pnl_usd"],
                    "reason": trade["reason"]
                })

        print(
            ticker,
            "V5:", v5_result["total_return_pct"],
            "V6:", v6_result["total_return_pct"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    with (OUTPUT / "trades.csv").open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker",
                "model",
                "entry_date",
                "exit_date",
                "pnl_usd",
                "reason"
            ]
        )
        writer.writeheader()
        writer.writerows(all_trades)

    print("V5-V6 comparison completed")


if __name__ == "__main__":
    main()
