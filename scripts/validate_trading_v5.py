import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("data/trading_validation/summary.json")
OUTPUT = Path("data/trading_validation_v5")
TICKERS = ["FCEL", "APA", "NCNA", "SPCX", "NVDA", "MCHP"]

CAPITAL = 10000.0
COST = 0.001
STOP = 0.05
TARGET = 0.10
MAX_HOLD = 10
MAX_ALLOCATION = 0.20
RISK_LIMIT = 0.01
COOLDOWN = 5


def read_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ("open", "high", "low", "close"):
            row[key] = float(row[key])
    return rows


def drawdown(values):
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return round(worst * 100, 2)


def simulate(prices, start, end):
    cash = CAPITAL
    shares = 0.0
    entry = 0.0
    entry_cost = 0.0
    entry_day = -1
    exit_day = -1
    cooldown_until = -1
    losses = 0
    trades = []
    equity = [CAPITAL]

    for i in range(start, end + 1):
        day = prices[i]
        closed_today = False

        if shares > 0:
            stop_price = entry * (1 - STOP)
            target_price = entry * (1 + TARGET)
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
            elif i >= exit_day:
                exit_price = day["close"]
                reason = "time"

            if exit_price is not None:
                proceeds = shares * exit_price * (1 - COST)
                cash += proceeds
                pnl = proceeds - entry_cost
                trades.append({
                    "entry_date": prices[entry_day]["date"],
                    "exit_date": day["date"],
                    "pnl_usd": round(pnl, 2),
                    "reason": reason
                })

                if pnl < 0:
                    losses += 1
                else:
                    losses = 0

                if losses >= 3:
                    cooldown_until = i + COOLDOWN
                    losses = 0

                shares = 0.0
                closed_today = True

        if (
            shares == 0
            and not closed_today
            and i > start
            and i > cooldown_until
            and i >= 200
            and i + MAX_HOLD - 1 <= end
        ):
            history = [
                prices[j]["close"]
                for j in range(i - 200, i)
            ]
            sma20 = sum(history[-20:]) / 20
            sma50 = sum(history[-50:]) / 50
            sma200 = sum(history) / 200

            signal = (
                history[-1] > sma20
                and sma20 > sma50
                and history[-1] > sma200
            )

            if signal:
                price = day["open"]

                if price > 0 and math.isfinite(price):
                    risk_shares = (
                        cash * RISK_LIMIT / (price * STOP)
                    )
                    allocation_shares = (
                        cash * MAX_ALLOCATION / price
                    )
                    affordable_shares = (
                        cash / (price * (1 + COST))
                    )
                    amount = min(
                        risk_shares,
                        allocation_shares,
                        affordable_shares
                    )

                    if amount > 0:
                        shares = amount
                        entry = price
                        entry_day = i
                        exit_day = i + MAX_HOLD - 1
                        entry_cost = (
                            shares * entry * (1 + COST)
                        )
                        cash -= entry_cost

                        # Evaluate the entry-day range.
                        exit_price = None
                        reason = None

                        if day["low"] <= entry * (1 - STOP):
                            exit_price = entry * (1 - STOP)
                            reason = "stop"
                        elif day["high"] >= entry * (1 + TARGET):
                            exit_price = entry * (1 + TARGET)
                            reason = "target"

                        if exit_price is not None:
                            proceeds = (
                                shares * exit_price * (1 - COST)
                            )
                            cash += proceeds
                            pnl = proceeds - entry_cost

                            trades.append({
                                "entry_date": day["date"],
                                "exit_date": day["date"],
                                "pnl_usd": round(pnl, 2),
                                "reason": reason
                            })

                            if pnl < 0:
                                losses += 1
                            else:
                                losses = 0

                            if losses >= 3:
                                cooldown_until = i + COOLDOWN
                                losses = 0

                            shares = 0.0

        value = cash + shares * day["close"]
        equity.append(value)

    if shares > 0:
        proceeds = shares * prices[end]["close"] * (1 - COST)
        cash += proceeds
        pnl = proceeds - entry_cost

        trades.append({
            "entry_date": prices[entry_day]["date"],
            "exit_date": prices[end]["date"],
            "pnl_usd": round(pnl, 2),
            "reason": "final_close"
        })
        equity[-1] = cash

    wins = sum(t["pnl_usd"] > 0 for t in trades)

    return {
        "start_date": prices[start]["date"],
        "end_date": prices[end]["date"],
        "initial_capital_usd": CAPITAL,
        "ending_capital_usd": round(cash, 2),
        "return_pct": round(
            (cash / CAPITAL - 1) * 100, 2
        ),
        "trade_count": len(trades),
        "win_rate_pct": round(
            100 * wins / len(trades), 2
        ) if trades else None,
        "daily_close_drawdown_pct": drawdown(equity),
        "trades": trades
    }


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            "Run stocks-trading-validation first"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)

    previous = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "method": "common_period_v1_to_v5",
        "by_ticker": {},
        "notes": [
            "Retrospective comparison, not independent validation.",
            "V1-V4 results are reused from prior validation.",
            "V5 is simulated on matching date ranges.",
            "Daily drawdown uses closing equity only.",
            "Different position sizing across models.",
            "No taxes, FX costs, or market impact.",
            "Historical adjusted prices approximate execution."
        ]
    }

    all_trades = []

    for ticker in TICKERS:
        old = previous["by_ticker"].get(ticker)

        if not old:
            print("No prior validation:", ticker)
            continue

        prices = read_prices(ticker)
        index = {
            row["date"]: i
            for i, row in enumerate(prices)
        }

        start_date = old["V1"]["start_date"]
        end_date = old["V1"]["end_date"]

        if start_date not in index or end_date not in index:
            print("Date mismatch:", ticker)
            continue

        start = index[start_date]
        end = index[end_date]

        report["by_ticker"][ticker] = dict(old)

        if end - start < 10:
            print("Short period:", ticker)
            continue

        if len(prices) < 201:
            report["by_ticker"][ticker]["V5"] = {
                "status": "insufficient_200_day_history",
                "start_date": start_date,
                "end_date": end_date
            }
            continue

        result = simulate(prices, start, end)
        trades = result.pop("trades")
        report["by_ticker"][ticker]["V5"] = result

        for trade in trades:
            all_trades.append({
                "ticker": ticker,
                "model": "V5",
                **trade
            })

        print(
            ticker,
            "V5 return:", result["return_pct"],
            "trades:", result["trade_count"]
        )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "model", "entry_date",
        "exit_date", "pnl_usd", "reason"
    ]

    with (OUTPUT / "trades_v5.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_trades)

    print("V1-V5 validation completed")


if __name__ == "__main__":
    main()
