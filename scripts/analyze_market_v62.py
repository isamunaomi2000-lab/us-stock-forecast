import csv
import json
import math
import statistics
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6

OUTPUT = Path("data/market_analysis_v62")
WARMUP = 200
TEST_FRACTION = 0.20


def load_spy():
    with Path("data/stocks/SPY.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        rows = list(csv.DictReader(f))

    dates = [r["date"] for r in rows]
    closes = [float(r["close"]) for r in rows]

    if dates != sorted(dates):
        raise ValueError("SPY dates are not sorted")

    return dates, closes


def market_state(date, dates, closes):
    # Use only completed SPY sessions before entry.
    pos = bisect_left(dates, date)
    if pos < 201:
        return None

    past = closes[pos - 201:pos]
    if min(past) <= 0:
        return None

    sma50 = statistics.mean(past[-50:])
    sma200 = statistics.mean(past[-200:])
    momentum20 = past[-1] / past[-21] - 1

    returns = [
        math.log(past[j] / past[j - 1])
        for j in range(len(past) - 20, len(past))
    ]
    volatility20 = (
        statistics.stdev(returns) * math.sqrt(252)
    )

    return {
        "above_sma200": past[-1] > sma200,
        "sma50_above_sma200": sma50 > sma200,
        "momentum20_positive": momentum20 > 0,
        "volatility20_high": volatility20 >= 0.25,
        "spy_momentum20_pct": round(momentum20 * 100, 2),
        "spy_volatility20_pct": round(
            volatility20 * 100, 2
        )
    }


def summarize(trades):
    count = len(trades)
    pnl = sum(t["pnl_usd"] for t in trades)
    wins = sum(t["pnl_usd"] > 0 for t in trades)
    return {
        "trades": count,
        "pnl_usd": round(pnl, 2),
        "win_rate_pct": (
            round(100 * wins / count, 2)
            if count else None
        ),
        "average_pnl_usd": (
            round(pnl / count, 2) if count else None
        )
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dates, closes = load_spy()

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "strategy": "v62_market_regime_diagnostics",
        "period": "last_20_percent_of_ticker_history",
        "volatility_high_threshold_pct": 25,
        "by_ticker": {},
        "notes": [
            "Diagnostic analysis, not a trading strategy.",
            "Uses original V6 trades without modification.",
            "Market state uses only SPY history before entry.",
            "Trade PnL is grouped by entry-date conditions.",
            "Results are descriptive, not causal.",
            "The 25 percent volatility threshold is exploratory.",
            "No independent holdout validation."
        ]
    }
    details = []

    for ticker in v6.TICKERS:
        prices = v6.load_prices(ticker)
        if len(prices) < 250:
            report["by_ticker"][ticker] = {
                "status": "insufficient_history",
                "rows": len(prices)
            }
            continue

        start = max(
            int(len(prices) * (1 - TEST_FRACTION)),
            WARMUP
        )
        window = prices[start - WARMUP:]
        result, trades = v6.simulate(window)

        enriched = []
        for trade in trades:
            state = market_state(
                trade["entry_date"], dates, closes
            )
            if state is None:
                continue

            record = {
                "ticker": ticker,
                **trade,
                **state
            }
            enriched.append(record)
            details.append(record)

        groups = {}
        for field in [
            "above_sma200",
            "sma50_above_sma200",
            "momentum20_positive",
            "volatility20_high"
        ]:
            groups[field] = {}
            for value in (True, False):
                subset = [
                    t for t in enriched
                    if t[field] == value
                ]
                groups[field][str(value).lower()] = (
                    summarize(subset)
                )

        years = {}
        for year in sorted({
            t["entry_date"][:4] for t in enriched
        }):
            years[year] = summarize([
                t for t in enriched
                if t["entry_date"].startswith(year)
            ])

        report["by_ticker"][ticker] = {
            "start_date": prices[start]["date"],
            "end_date": prices[-1]["date"],
            "v6_return_pct": result["total_return_pct"],
            "v6_max_drawdown_pct": (
                result["max_daily_close_drawdown_pct"]
            ),
            "total_trades": len(trades),
            "classified_trades": len(enriched),
            "unclassified_trades": (
                len(trades) - len(enriched)
            ),
            "by_market_condition": groups,
            "by_entry_year": years
        }

        print(
            ticker,
            "trades:", len(trades),
            "classified:", len(enriched)
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "entry_date", "exit_date",
        "pnl_usd", "reason",
        "above_sma200", "sma50_above_sma200",
        "momentum20_positive", "volatility20_high",
        "spy_momentum20_pct", "spy_volatility20_pct"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(details)

    print("V6.2 market analysis completed")


if __name__ == "__main__":
    main()
