import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]

INITIAL_CAPITAL = 10000.0
COST_PER_SIDE = 0.001
TAKE_PROFIT = 0.10
STOP_LOSS = 0.05
MAX_HOLD_DAYS = 10

OUTPUT = Path("data/trading_simulation_v4")


def average(values):
    return sum(values) / len(values)


def max_drawdown(values):
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return round(worst * 100, 2)


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        for key in ("open", "high", "low", "close"):
            row[key] = float(row[key])

    return rows


def simulate(rows):
    capital = INITIAL_CAPITAL
    equity = [capital]
    trades = []

    # Signals require 50 completed sessions.
    i = 49

    while i + 1 < len(rows):
        closes = [r["close"] for r in rows[i - 49:i + 1]]

        sma20 = average(closes[-20:])
        sma50 = average(closes[-50:])
        signal = closes[-1] > sma20 > sma50

        if not signal:
            i += 1
            continue

        entry_index = i + 1
        entry = rows[entry_index]["open"]

        if entry <= 0 or not math.isfinite(entry):
            i += 1
            continue

        stop_price = entry * (1 - STOP_LOSS)
        target_price = entry * (1 + TAKE_PROFIT)

        last_index = min(
            entry_index + MAX_HOLD_DAYS - 1,
            len(rows) - 1
        )

        exit_index = last_index
        exit_price = rows[last_index]["close"]
        reason = "time_exit"

        for j in range(entry_index, last_index + 1):
            day = rows[j]

            # Gap at the open: fill at opening price.
            if day["open"] <= stop_price:
                exit_index = j
                exit_price = day["open"]
                reason = "stop_gap"
                break

            if day["open"] >= target_price:
                exit_index = j
                exit_price = day["open"]
                reason = "target_gap"
                break

            # If both levels touch, assume stop first.
            if day["low"] <= stop_price:
                exit_index = j
                exit_price = stop_price
                reason = "stop_loss"
                break

            if day["high"] >= target_price:
                exit_index = j
                exit_price = target_price
                reason = "take_profit"
                break

        if exit_price <= 0 or not math.isfinite(exit_price):
            raise ValueError("Invalid exit price")

        factor = (
            exit_price / entry
            * (1 - COST_PER_SIDE) ** 2
        )

        capital *= factor
        equity.append(capital)

        trades.append({
            "entry_date": rows[entry_index]["date"],
            "exit_date": rows[exit_index]["date"],
            "entry_price": round(entry, 6),
            "exit_price": round(exit_price, 6),
            "reason": reason,
            "return_pct": round((factor - 1) * 100, 4),
            "equity_after": round(capital, 2)
        })

        # Do not overlap trades. Re-enter only after
        # a new signal based on a completed session.
        i = exit_index + 1

    wins = sum(t["return_pct"] > 0 for t in trades)

    start_price = rows[50]["open"]
    end_price = rows[-1]["close"]

    buy_hold = (
        end_price / start_price
        * (1 - COST_PER_SIDE) ** 2 - 1
    ) * 100

    return {
        "initial_capital_usd": INITIAL_CAPITAL,
        "ending_capital_usd": round(capital, 2),
        "total_return_pct": round(
            (capital / INITIAL_CAPITAL - 1) * 100, 2
        ),
        "buy_and_hold_return_pct": round(buy_hold, 2),
        "trade_count": len(trades),
        "win_rate_pct": round(
            100 * wins / len(trades), 2
        ) if trades else None,
        "max_closed_trade_drawdown_pct": max_drawdown(equity),
        "first_price_date": rows[0]["date"],
        "last_price_date": rows[-1]["date"],
        "trades": trades
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "strategy": "experimental_sma20_sma50_v4",
        "assumptions": {
            "initial_capital_usd": INITIAL_CAPITAL,
            "take_profit_pct": TAKE_PROFIT * 100,
            "stop_loss_pct": STOP_LOSS * 100,
            "max_holding_sessions": MAX_HOLD_DAYS,
            "cost_per_side_pct": COST_PER_SIDE * 100,
            "long_only": True,
            "next_open_entry": True
        },
        "by_ticker": {},
        "notes": [
            "Historical simulation only.",
            "Parameters have not been independently validated.",
            "Signals use completed daily candles.",
            "Entry occurs at next session open.",
            "Stops and targets use daily OHLC approximation.",
            "Stop is assumed first when both levels touch.",
            "Gap fills use opening price.",
            "No leverage or overlapping trades.",
            "Full historical period, not independent test.",
            "Drawdown uses closed-trade equity only.",
            "No taxes, FX costs, or market impact.",
            "Adjusted historical prices may be revised."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        rows = load_prices(ticker)

        if len(rows) < 52:
            print("Insufficient data:", ticker)
            continue

        result = simulate(rows)
        trades = result.pop("trades")
        report["by_ticker"][ticker] = result

        for trade in trades:
            all_trades.append({
                "ticker": ticker,
                **trade
            })

        print(
            ticker,
            "return:", result["total_return_pct"],
            "trades:", result["trade_count"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "entry_date", "exit_date",
        "entry_price", "exit_price",
        "reason", "return_pct", "equity_after"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_trades)

    print("V4 simulation completed")


if __name__ == "__main__":
    main()
