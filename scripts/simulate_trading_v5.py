import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]

INITIAL_CAPITAL = 10000.0
COST_PER_SIDE = 0.001
RISK_PER_TRADE = 0.01
MAX_ALLOCATION = 0.20
STOP_LOSS = 0.05
TAKE_PROFIT = 0.10
MAX_HOLD_DAYS = 10
LOSS_STREAK_LIMIT = 3
COOLDOWN_DAYS = 5

OUTPUT = Path("data/trading_simulation_v5")


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        for key in ("open", "high", "low", "close"):
            row[key] = float(row[key])

    return rows


def average(values):
    return sum(values) / len(values)


def maximum_drawdown(values):
    peak = values[0]
    worst = 0.0

    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)

    return round(worst * 100, 2)


def simulate(rows):
    cash = INITIAL_CAPITAL
    shares = 0.0
    entry_price = 0.0
    entry_index = -1
    last_exit_index = -1
    cooldown_until = -1
    consecutive_losses = 0

    trades = []
    equity_curve = [INITIAL_CAPITAL]

    # Need 200 completed daily sessions.
    for i in range(199, len(rows)):
        day = rows[i]

        # Existing position: check exit conditions.
        if shares > 0:
            stop = entry_price * (1 - STOP_LOSS)
            target = entry_price * (1 + TAKE_PROFIT)

            exit_price = None
            reason = None

            if day["open"] <= stop:
                exit_price = day["open"]
                reason = "stop_gap"
            elif day["open"] >= target:
                exit_price = day["open"]
                reason = "target_gap"
            elif day["low"] <= stop:
                exit_price = stop
                reason = "stop_loss"
            elif day["high"] >= target:
                exit_price = target
                reason = "take_profit"
            elif i - entry_index + 1 >= MAX_HOLD_DAYS:
                exit_price = day["close"]
                reason = "time_exit"

            if exit_price is not None:
                proceeds = shares * exit_price * (
                    1 - COST_PER_SIDE
                )
                cash += proceeds

                net_factor = (
                    exit_price / entry_price
                    * (1 - COST_PER_SIDE) ** 2
                )

                trade_return = (net_factor - 1) * 100
                pnl = proceeds - entry_cost

                trades.append({
                    "entry_date": rows[entry_index]["date"],
                    "exit_date": day["date"],
                    "entry_price": round(entry_price, 6),
                    "exit_price": round(exit_price, 6),
                    "shares": round(shares, 8),
                    "pnl_usd": round(pnl, 2),
                    "return_pct": round(trade_return, 4),
                    "reason": reason,
                    "equity_after": round(cash, 2)
                })

                if pnl < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                if consecutive_losses >= LOSS_STREAK_LIMIT:
                    cooldown_until = i + COOLDOWN_DAYS
                    consecutive_losses = 0

                shares = 0.0
                last_exit_index = i

        # Signal uses previous day's completed candle.
        if (
            shares == 0
            and i > 199
            and i > last_exit_index
            and i > cooldown_until
        ):
            closes = [
                rows[k]["close"]
                for k in range(i - 200, i)
            ]

            sma20 = average(closes[-20:])
            sma50 = average(closes[-50:])
            sma200 = average(closes)

            signal = (
                closes[-1] > sma20
                and sma20 > sma50
                and closes[-1] > sma200
            )

            if signal and i + MAX_HOLD_DAYS - 1 < len(rows):
                price = day["open"]

                if price > 0 and math.isfinite(price):
                    # Maximum risk is based on stop distance.
                    risk_budget = cash * RISK_PER_TRADE
                    risk_per_share = price * STOP_LOSS

                    risk_shares = (
                        risk_budget / risk_per_share
                    )
                    allocation_shares = (
                        cash * MAX_ALLOCATION / price
                    )

                    desired_shares = min(
                        risk_shares,
                        allocation_shares
                    )

                    # Include entry cost in affordability.
                    affordable_shares = cash / (
                        price * (1 + COST_PER_SIDE)
                    )
                    shares = min(
                        desired_shares,
                        affordable_shares
                    )

                    if shares > 0:
                        entry_price = price
                        entry_index = i
                        entry_cost = (
                            shares * price
                            * (1 + COST_PER_SIDE)
                        )
                        cash -= entry_cost

                        # Intraday stop/target on entry day.
                        stop = price * (1 - STOP_LOSS)
                        target = price * (1 + TAKE_PROFIT)

                        exit_price = None
                        reason = None

                        if day["low"] <= stop:
                            exit_price = stop
                            reason = "stop_loss"
                        elif day["high"] >= target:
                            exit_price = target
                            reason = "take_profit"

                        if exit_price is not None:
                            proceeds = shares * exit_price * (
                                1 - COST_PER_SIDE
                            )
                            cash += proceeds
                            pnl = proceeds - entry_cost
                            factor = (
                                exit_price / price
                                * (1 - COST_PER_SIDE) ** 2
                            )

                            trades.append({
                                "entry_date": day["date"],
                                "exit_date": day["date"],
                                "entry_price": round(price, 6),
                                "exit_price": round(
                                    exit_price, 6
                                ),
                                "shares": round(shares, 8),
                                "pnl_usd": round(pnl, 2),
                                "return_pct": round(
                                    (factor - 1) * 100, 4
                                ),
                                "reason": reason,
                                "equity_after": round(cash, 2)
                            })

                            if pnl < 0:
                                consecutive_losses += 1
                            else:
                                consecutive_losses = 0

                            if (
                                consecutive_losses
                                >= LOSS_STREAK_LIMIT
                            ):
                                cooldown_until = (
                                    i + COOLDOWN_DAYS
                                )
                                consecutive_losses = 0

                            shares = 0.0
                            last_exit_index = i

        equity = cash + shares * day["close"]
        equity_curve.append(equity)

    # Liquidate any open position at the final close.
    if shares > 0:
        final_price = rows[-1]["close"]
        proceeds = shares * final_price * (
            1 - COST_PER_SIDE
        )
        cash += proceeds
        pnl = proceeds - entry_cost

        factor = (
            final_price / entry_price
            * (1 - COST_PER_SIDE) ** 2
        )

        trades.append({
            "entry_date": rows[entry_index]["date"],
            "exit_date": rows[-1]["date"],
            "entry_price": round(entry_price, 6),
            "exit_price": round(final_price, 6),
            "shares": round(shares, 8),
            "pnl_usd": round(pnl, 2),
            "return_pct": round((factor - 1) * 100, 4),
            "reason": "final_close",
            "equity_after": round(cash, 2)
        })

        equity_curve[-1] = cash

    wins = sum(t["pnl_usd"] > 0 for t in trades)

    return {
        "initial_capital_usd": INITIAL_CAPITAL,
        "ending_capital_usd": round(cash, 2),
        "total_return_pct": round(
            (cash / INITIAL_CAPITAL - 1) * 100, 2
        ),
        "trade_count": len(trades),
        "win_rate_pct": round(
            wins / len(trades) * 100, 2
        ) if trades else None,
        "max_daily_close_drawdown_pct": maximum_drawdown(
            equity_curve
        ),
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
        "strategy": "experimental_risk_managed_v5",
        "assumptions": {
            "initial_capital_usd": INITIAL_CAPITAL,
            "risk_per_trade_pct": RISK_PER_TRADE * 100,
            "max_allocation_pct": MAX_ALLOCATION * 100,
            "stop_loss_pct": STOP_LOSS * 100,
            "take_profit_pct": TAKE_PROFIT * 100,
            "max_holding_sessions": MAX_HOLD_DAYS,
            "cost_per_side_pct": COST_PER_SIDE * 100,
            "loss_streak_limit": LOSS_STREAK_LIMIT,
            "cooldown_sessions": COOLDOWN_DAYS,
            "long_only": True
        },
        "by_ticker": {},
        "notes": [
            "Historical simulation only.",
            "No independent holdout validation.",
            "One percent is a target, not a guaranteed loss cap.",
            "Position size is limited to twenty percent.",
            "Daily closing equity approximates drawdown.",
            "Daily OHLC approximates stop and target fills.",
            "If both stop and target touch, stop wins.",
            "No taxes, FX costs, or market impact.",
            "Adjusted prices may change retrospectively."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        rows = load_prices(ticker)

        if len(rows) < 202:
            print("Insufficient history:", ticker)
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
        "entry_price", "exit_price", "shares",
        "pnl_usd", "return_pct", "reason",
        "equity_after"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_trades)

    print("V5 simulation completed")


if __name__ == "__main__":
    main()
