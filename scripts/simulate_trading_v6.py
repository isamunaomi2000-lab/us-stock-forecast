import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]
CAPITAL = 10000.0
FEE = 0.001
MAX_ALLOCATION = 0.20
RISK_PER_TRADE = 0.01
STOP = 0.05
TARGET = 0.10
MAX_HOLD = 10
COOLDOWN = 5
OUTPUT = Path("data/trading_simulation_v6")


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ("open", "high", "low", "close", "volume"):
            row[key] = float(row[key])
    return rows


def rsi14(closes):
    changes = [
        closes[i] - closes[i - 1]
        for i in range(len(closes) - 14, len(closes))
    ]
    gain = sum(max(x, 0) for x in changes) / 14
    loss = sum(max(-x, 0) for x in changes) / 14
    if gain == 0 and loss == 0:
        return 50.0
    if loss == 0:
        return 100.0
    return 100 - 100 / (1 + gain / loss)


def signal_at(rows, i):
    # Only use completed sessions before entry day i.
    past = rows[i - 200:i]
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

    rsi = rsi14(closes)
    momentum = closes[-1] / closes[-21] - 1

    avg_volume = statistics.mean(volumes[-21:-1])
    volume_ok = (
        avg_volume > 0
        and volumes[-1] >= 1.2 * avg_volume
    )

    returns = [
        math.log(closes[j] / closes[j - 1])
        for j in range(len(closes) - 20, len(closes))
    ]
    volatility = statistics.stdev(returns) * math.sqrt(252)

    return (
        trend
        and 45 <= rsi <= 70
        and momentum >= 0.03
        and volume_ok
        and volatility <= 0.80
    )


def max_drawdown(values):
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return round(worst * 100, 2)


def simulate(rows):
    cash = CAPITAL
    shares = 0.0
    entry_price = 0.0
    entry_cost = 0.0
    entry_i = -1
    cooldown_until = -1
    losses = 0
    trades = []
    equity = [CAPITAL]

    for i in range(200, len(rows)):
        day = rows[i]
        exited_today = False

        if shares > 0:
            stop_price = entry_price * (1 - STOP)
            target_price = entry_price * (1 + TARGET)
            exit_price = None
            reason = None

            if day["open"] <= stop_price:
                exit_price = day["open"]
                reason = "stop_gap"
            elif day["open"] >= target_price:
                exit_price = day["open"]
                reason = "target_gap"
            elif day["low"] <= stop_price:
                exit_price = stop_price
                reason = "stop"
            elif day["high"] >= target_price:
                exit_price = target_price
                reason = "target"
            elif i - entry_i + 1 >= MAX_HOLD:
                exit_price = day["close"]
                reason = "time"

            if exit_price is not None:
                proceeds = shares * exit_price * (1 - FEE)
                cash += proceeds
                pnl = proceeds - entry_cost
                trades.append({
                    "entry_date": rows[entry_i]["date"],
                    "exit_date": day["date"],
                    "pnl_usd": round(pnl, 2),
                    "reason": reason
                })

                losses = losses + 1 if pnl < 0 else 0
                if losses >= 3:
                    cooldown_until = i + COOLDOWN
                    losses = 0

                shares = 0.0
                exited_today = True

        if (
            shares == 0
            and not exited_today
            and i > cooldown_until
            and i + MAX_HOLD - 1 < len(rows)
            and signal_at(rows, i)
        ):
            price = day["open"]

            if price > 0 and math.isfinite(price):
                risk_shares = cash * RISK_PER_TRADE / (price * STOP)
                allocation_shares = cash * MAX_ALLOCATION / price
                affordable = cash / (price * (1 + FEE))
                amount = min(
                    risk_shares, allocation_shares, affordable
                )

                if amount > 0:
                    shares = amount
                    entry_price = price
                    entry_i = i
                    entry_cost = shares * price * (1 + FEE)
                    cash -= entry_cost

                    # Same-day stop/target approximation.
                    exit_price = None
                    reason = None

                    if day["low"] <= price * (1 - STOP):
                        exit_price = price * (1 - STOP)
                        reason = "stop"
                    elif day["high"] >= price * (1 + TARGET):
                        exit_price = price * (1 + TARGET)
                        reason = "target"

                    if exit_price is not None:
                        proceeds = shares * exit_price * (1 - FEE)
                        cash += proceeds
                        pnl = proceeds - entry_cost
                        trades.append({
                            "entry_date": day["date"],
                            "exit_date": day["date"],
                            "pnl_usd": round(pnl, 2),
                            "reason": reason
                        })
                        losses = losses + 1 if pnl < 0 else 0
                        if losses >= 3:
                            cooldown_until = i + COOLDOWN
                            losses = 0
                        shares = 0.0

        equity.append(cash + shares * day["close"])

    if shares > 0:
        proceeds = shares * rows[-1]["close"] * (1 - FEE)
        cash += proceeds
        pnl = proceeds - entry_cost
        trades.append({
            "entry_date": rows[entry_i]["date"],
            "exit_date": rows[-1]["date"],
            "pnl_usd": round(pnl, 2),
            "reason": "final_close"
        })
        equity[-1] = cash

    wins = sum(t["pnl_usd"] > 0 for t in trades)

    return {
        "initial_capital_usd": CAPITAL,
        "ending_capital_usd": round(cash, 2),
        "total_return_pct": round(
            100 * (cash / CAPITAL - 1), 2
        ),
        "trade_count": len(trades),
        "win_rate_pct": (
            round(100 * wins / len(trades), 2)
            if trades else None
        ),
        "max_daily_close_drawdown_pct": max_drawdown(equity),
        "first_price_date": rows[0]["date"],
        "last_price_date": rows[-1]["date"]
    }, trades


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "strategy": "experimental_v6_filtered",
        "assumptions": {
            "initial_capital_usd": CAPITAL,
            "max_allocation_pct": 20,
            "risk_per_trade_pct": 1,
            "stop_loss_pct": 5,
            "take_profit_pct": 10,
            "max_holding_sessions": 10,
            "cost_per_side_pct": 0.1,
            "rsi_range": [45, 70],
            "minimum_20_session_momentum_pct": 3,
            "minimum_volume_multiple": 1.2,
            "maximum_annualized_volatility_pct": 80
        },
        "by_ticker": {},
        "notes": [
            "Experimental historical simulation only.",
            "No independent holdout validation.",
            "No future data used in entry signals.",
            "Daily OHLC approximates stop and target fills.",
            "One percent risk is a target, not a guarantee.",
            "No taxes, FX fees, or market impact."
        ]
    }
    all_trades = []

    for ticker in TICKERS:
        rows = load_prices(ticker)
        if len(rows) < 211:
            print("Insufficient history:", ticker)
            continue

        result, trades = simulate(rows)
        report["by_ticker"][ticker] = result

        for trade in trades:
            all_trades.append({"ticker": ticker, **trade})

        print(
            ticker,
            "return:", result["total_return_pct"],
            "trades:", result["trade_count"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "entry_date", "exit_date",
                "pnl_usd", "reason"
            ]
        )
        writer.writeheader()
        writer.writerows(all_trades)

    print("V6 simulation completed")


if __name__ == "__main__":
    main()
