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


def run_model(simulator, prices, start):
    # Preserve 200 sessions of indicator warm-up.
    # Prevent trading before the common comparison date.
    window = prices[start - 200:]
    result = simulator(window)

    if isinstance(result, tuple):
        summary, trades = result
    else:
        summary = dict(result)
        trades = summary.pop("trades", [])

    return summary, trades


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "last_20_percent_comparison_v5_v6",
        "by_ticker": {},
        "notes": [
            "Retrospective comparison only.",
            "Not an independent unseen-data test.",
            "Same starting capital and risk settings.",
            "Warm-up sessions are retained.",
            "Signals use prior completed sessions.",
            "No taxes, FX costs, or market impact."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        prices = load_prices(ticker)
        n = len(prices)

        if n < 250:
            report["by_ticker"][ticker] = {
                "status": "insufficient_history"
            }
            continue

        start = max(200, int(n * 0.8))

        # Ensure the first simulation session is at
        # the same original date for both models.
        # V5 starts its loop at index 199.
        # V6 starts its loop at index 200.
        # Shift the V5 input by one session.
        v5_window = prices[start - 199:]
        v6_window = prices[start - 200:]

        v5 = simulate_v5(v5_window)
        v5_trades = v5.pop("trades", [])

        v6, v6_trades = simulate_v6(v6_window)

        report["by_ticker"][ticker] = {
            "start_date": prices[start]["date"],
            "end_date": prices[-1]["date"],
            "V5": v5,
            "V6": v6
        }

        for model, trades in (
            ("V5", v5_trades),
            ("V6", v6_trades)
        ):
            for trade in trades:
                all_trades.append({
                    "ticker": ticker,
                    "model": model,
                    **trade
                })

        print(
            ticker,
            "V5:", v5["total_return_pct"],
            "V6:", v6["total_return_pct"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "model", "entry_date",
        "exit_date", "pnl_usd", "reason"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(all_trades)

    print("V5-V6 comparison completed")


if __name__ == "__main__":
    main()
