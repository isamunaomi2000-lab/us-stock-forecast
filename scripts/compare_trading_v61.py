import csv
import json
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6

OUTPUT = Path("data/trading_comparison_v61")
TICKERS = v6.TICKERS
WARMUP = 200
TEST_FRACTION = 0.20


def load_spy():
    path = Path("data/stocks/SPY.csv")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    dates = [row["date"] for row in rows]
    closes = [float(row["close"]) for row in rows]

    if dates != sorted(dates):
        raise ValueError("SPY dates are not sorted")

    return dates, closes


def spy_trend_ok(date, dates, closes):
    # Only SPY sessions strictly before the entry date.
    pos = bisect_left(dates, date)

    if pos < 200:
        return False

    previous_close = closes[pos - 1]
    sma200 = sum(closes[pos - 200:pos]) / 200

    return previous_close > sma200


def simulate_with_market_filter(rows, spy_dates, spy_closes):
    original_signal = v6.signal_at

    def filtered_signal(price_rows, i):
        if not original_signal(price_rows, i):
            return False

        return spy_trend_ok(
            price_rows[i]["date"],
            spy_dates,
            spy_closes
        )

    try:
        v6.signal_at = filtered_signal
        return v6.simulate(rows)
    finally:
        v6.signal_at = original_signal


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    spy_dates, spy_closes = load_spy()

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "strategy": "v6_vs_v61_spy_trend",
        "market_filter": (
            "SPY previous completed close > "
            "SPY previous 200-session SMA"
        ),
        "test_fraction": TEST_FRACTION,
        "by_ticker": {},
        "notes": [
            "Historical comparison, not live signals.",
            "Both strategies use the same V6 execution.",
            "Last 20 percent of each ticker's history.",
            "200 prior ticker sessions for warm-up.",
            "SPY filter uses dates strictly before entry.",
            "This is not independent holdout validation.",
            "Daily OHLC execution is approximate."
        ]
    }

    output_rows = []

    for ticker in TICKERS:
        prices = v6.load_prices(ticker)

        if len(prices) < 250:
            report["by_ticker"][ticker] = {
                "status": "insufficient_history",
                "available_rows": len(prices)
            }
            continue

        start = int(len(prices) * (1 - TEST_FRACTION))
        start = max(start, WARMUP)

        window = prices[start - WARMUP:]

        # Both strategies use exactly the same price window.
        baseline, baseline_trades = v6.simulate(window)
        filtered, filtered_trades = simulate_with_market_filter(
            window, spy_dates, spy_closes
        )

        result = {
            "start_date": prices[start]["date"],
            "end_date": prices[-1]["date"],
            "v6": baseline,
            "v61": filtered,
            "return_difference_pp": round(
                filtered["total_return_pct"]
                - baseline["total_return_pct"], 2
            ),
            "drawdown_difference_pp": round(
                filtered["max_daily_close_drawdown_pct"]
                - baseline["max_daily_close_drawdown_pct"], 2
            )
        }

        report["by_ticker"][ticker] = result

        for name, stats in (
            ("V6", baseline),
            ("V6.1", filtered)
        ):
            output_rows.append({
                "ticker": ticker,
                "model": name,
                "start_date": result["start_date"],
                "end_date": result["end_date"],
                "return_pct": stats["total_return_pct"],
                "drawdown_pct": (
                    stats["max_daily_close_drawdown_pct"]
                ),
                "win_rate_pct": stats["win_rate_pct"],
                "trade_count": stats["trade_count"]
            })

        print(
            ticker,
            "V6:", baseline["total_return_pct"],
            "V6.1:", filtered["total_return_pct"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    with (OUTPUT / "results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "model", "start_date",
                "end_date", "return_pct", "drawdown_pct",
                "win_rate_pct", "trade_count"
            ]
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print("V6 vs V6.1 comparison completed")


if __name__ == "__main__":
    main()
