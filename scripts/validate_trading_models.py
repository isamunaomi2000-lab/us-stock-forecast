import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
MODELS = ["V1", "V2", "V3", "V4"]
CAPITAL = 10000.0
COST = 0.001
OUTPUT = Path("data/trading_validation")


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def drawdown(values):
    peak = values[0]
    worst = 0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return round(worst * 100, 2)


def run(prices, forecasts, model, start, end):
    cash = CAPITAL
    shares = 0.0
    entry = 0.0
    entry_day = -1
    exit_day = -1
    trades = []
    equity = [CAPITAL]
    dates = []

    for i in range(start, end + 1):
        day = prices[i]
        date = day["date"]
        close = day["close"]

        # Exit existing position at the daily open or
        # stop/target level; V1-V3 exit after 5 sessions.
        if shares > 0:
            exit_price = None
            reason = None

            if model == "V4":
                stop = entry * 0.95
                target = entry * 1.10

                if day["open"] <= stop:
                    exit_price = day["open"]
                    reason = "stop_gap"
                elif day["open"] >= target:
                    exit_price = day["open"]
                    reason = "target_gap"
                elif day["low"] <= stop:
                    exit_price = stop
                    reason = "stop"
                elif day["high"] >= target:
                    exit_price = target
                    reason = "target"
                elif i >= exit_day:
                    exit_price = close
                    reason = "time"
            elif i >= exit_day:
                exit_price = close
                reason = "time"

            if exit_price is not None:
                cash = shares * exit_price * (1 - COST)
                factor = (
                    exit_price / entry
                    * (1 - COST) ** 2
                )
                trades.append({
                    "model": model,
                    "entry_date": prices[entry_day]["date"],
                    "exit_date": date,
                    "return_pct": round((factor - 1) * 100, 4),
                    "reason": reason
                })
                shares = 0.0

        # Entry at today's open using yesterday's signal.
        if shares == 0 and i > start:
            signal_day = i - 1
            signal_date = prices[signal_day]["date"]
            should_buy = False

            if model == "V4" and signal_day >= 49:
                closes = [
                    prices[k]["close"]
                    for k in range(signal_day - 49, signal_day + 1)
                ]
                sma20 = sum(closes[-20:]) / 20
                sma50 = sum(closes) / 50
                should_buy = closes[-1] > sma20 > sma50

            elif model != "V4":
                prediction = forecasts.get(
                    (signal_date, model)
                )
                should_buy = (
                    prediction is not None
                    and prediction > prices[signal_day]["close"]
                )

            # Only open trades that can finish in the
            # selected validation window.
            horizon = 10 if model == "V4" else 5
            if should_buy and i + horizon - 1 <= end:
                entry = day["open"]
                if entry > 0 and math.isfinite(entry):
                    shares = cash * (1 - COST) / entry
                    cash = 0.0
                    entry_day = i
                    exit_day = i + horizon - 1

                    # Handle same-day V4 stop/target.
                    if model == "V4":
                        if day["low"] <= entry * 0.95:
                            price = entry * 0.95
                            reason = "stop"
                        elif day["high"] >= entry * 1.10:
                            price = entry * 1.10
                            reason = "target"
                        else:
                            price = None

                        if price is not None:
                            cash = shares * price * (1 - COST)
                            factor = (
                                price / entry * (1 - COST) ** 2
                            )
                            trades.append({
                                "model": model,
                                "entry_date": date,
                                "exit_date": date,
                                "return_pct": round(
                                    (factor - 1) * 100, 4
                                ),
                                "reason": reason
                            })
                            shares = 0.0

        value = cash if shares == 0 else shares * close
        equity.append(value)
        dates.append(date)

    final = equity[-1]
    wins = sum(t["return_pct"] > 0 for t in trades)

    return {
        "start_date": prices[start]["date"],
        "end_date": prices[end]["date"],
        "initial_capital_usd": CAPITAL,
        "ending_capital_usd": round(final, 2),
        "return_pct": round((final / CAPITAL - 1) * 100, 2),
        "trade_count": len(trades),
        "win_rate_pct": round(
            100 * wins / len(trades), 2
        ) if trades else None,
        "daily_close_drawdown_pct": drawdown(equity),
        "trades": trades
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    raw = load_csv("data/model_comparison_v3/results.csv")
    grouped = defaultdict(dict)

    for row in raw:
        grouped[row["ticker"]][
            (row["forecast_date"], row["model"])
        ] = float(row["predicted"])

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "common_last_20_percent_of_available_forecasts",
        "by_ticker": {},
        "notes": [
            "Exploratory retrospective comparison only.",
            "The last 20 percent is not an untouched holdout.",
            "All models use the same dates per ticker.",
            "Daily drawdown uses closing prices, not intraday lows.",
            "Adjusted prices and daily OHLC approximate execution.",
            "No taxes, FX costs, or market impact.",
            "V1-V3 forecasts may have been developed using",
            "information from this historical evaluation.",
            "V4 rules were chosen after earlier results were seen."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        prices = load_csv(f"data/stocks/{ticker}.csv")
        for row in prices:
            for field in ("open", "high", "low", "close"):
                row[field] = float(row[field])

        predictions = grouped[ticker]
        dates = {
            date for date, model in predictions
            if model in ("V1", "V2", "V3")
        }
        common = sorted(
            date for date in dates
            if all(
                (date, model) in predictions
                for model in ("V1", "V2", "V3")
            )
        )

        if len(common) < 20:
            print("Insufficient history:", ticker)
            continue

        split = int(len(common) * 0.8)
        start_date = common[split]
        index = {
            row["date"]: i for i, row in enumerate(prices)
        }
        start = index[start_date]
        end = len(prices) - 1

        report["by_ticker"][ticker] = {}

        for model in MODELS:
            result = run(
                prices, predictions, model, start, end
            )
            trades = result.pop("trades")
            report["by_ticker"][ticker][model] = result

            for trade in trades:
                all_trades.append({
                    "ticker": ticker,
                    **trade
                })

            print(
                ticker, model,
                result["return_pct"],
                result["trade_count"]
            )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "model", "entry_date", "exit_date",
        "return_pct", "reason"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_trades)

    print("Validation completed")


if __name__ == "__main__":
    main()
