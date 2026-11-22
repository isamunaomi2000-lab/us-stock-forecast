import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

import simulate_trading_v6 as v6

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]

VARIANTS = [
    "baseline",
    "without_rsi",
    "without_volume",
    "without_momentum",
    "without_volatility",
]

OUTPUT = Path("data/v6_filter_analysis")


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        for key in ("open", "high", "low", "close", "volume"):
            row[key] = float(row[key])

    return rows


def make_signal(variant):
    def signal(rows, i):
        past = rows[i - 200:i]

        if len(past) != 200:
            return False

        closes = [r["close"] for r in past]
        volumes = [r["volume"] for r in past]

        if min(closes) <= 0:
            return False

        sma20 = statistics.mean(closes[-20:])
        sma50 = statistics.mean(closes[-50:])
        sma200 = statistics.mean(closes)

        trend = (
            closes[-1] > sma20
            and sma20 > sma50
            and closes[-1] > sma200
        )

        if not trend:
            return False

        rsi = v6.rsi14(closes)
        rsi_ok = 45 <= rsi <= 70

        momentum = closes[-1] / closes[-21] - 1
        momentum_ok = momentum >= 0.03

        avg_volume = statistics.mean(volumes[-21:-1])
        volume_ok = (
            avg_volume > 0
            and volumes[-1] >= 1.2 * avg_volume
        )

        returns = [
            math.log(closes[j] / closes[j - 1])
            for j in range(len(closes) - 20, len(closes))
        ]

        volatility = (
            statistics.stdev(returns) * math.sqrt(252)
        )
        volatility_ok = volatility <= 0.80

        conditions = {
            "without_rsi": rsi_ok,
            "without_volume": volume_ok,
            "without_momentum": momentum_ok,
            "without_volatility": volatility_ok,
        }

        for name, passed in conditions.items():
            if name != variant and not passed:
                return False

        return True

    return signal


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    original_signal = v6.signal_at

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "v6_one_filter_removed",
        "period": "last_20_percent",
        "by_ticker": {},
        "notes": [
            "Retrospective ablation analysis.",
            "Not independent out-of-sample validation.",
            "One filter removed at a time.",
            "Trend filter remains active.",
            "Same trading rules for all variants.",
            "Results do not prove future profitability."
        ]
    }

    flat_results = []

    try:
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

            start = max(200, int(n * 0.8))
            window = prices[start - 200:]

            ticker_report = {
                "start_date": prices[start]["date"],
                "end_date": prices[-1]["date"],
                "variants": {}
            }

            for variant in VARIANTS:
                v6.signal_at = make_signal(variant)

                result, trades = v6.simulate(window)

                ticker_report["variants"][variant] = result

                flat_results.append({
                    "ticker": ticker,
                    "variant": variant,
                    "start_date": prices[start]["date"],
                    "end_date": prices[-1]["date"],
                    "return_pct": result["total_return_pct"],
                    "drawdown_pct": result[
                        "max_daily_close_drawdown_pct"
                    ],
                    "win_rate_pct": result["win_rate_pct"],
                    "trade_count": result["trade_count"],
                })

                print(
                    ticker,
                    variant,
                    "return:",
                    result["total_return_pct"],
                    "trades:",
                    result["trade_count"]
                )

            report["by_ticker"][ticker] = ticker_report

    finally:
        v6.signal_at = original_signal

    (OUTPUT / "summary.json").write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    fields = [
        "ticker",
        "variant",
        "start_date",
        "end_date",
        "return_pct",
        "drawdown_pct",
        "win_rate_pct",
        "trade_count",
    ]

    with (OUTPUT / "results.csv").open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat_results)

    print("V6 filter analysis completed")


if __name__ == "__main__":
    main()
