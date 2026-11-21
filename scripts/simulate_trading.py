import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path("data/model_comparison_v3/results.csv")
OUTPUT = Path("data/trading_simulation")
OUTPUT.mkdir(parents=True, exist_ok=True)

MODELS = ["V1", "V2", "V3"]
INITIAL_CAPITAL = 10000.0
HORIZON = 5
COST_PER_SIDE = 0.001

# Signal at the forecast-date close.
# Trade at the NEXT session's open to avoid same-close execution.
# Hold for five sessions, exit at the fifth session's close.
# No leverage, short selling, or overlapping trades.


def load_prices(ticker):
    path = Path("data/stocks") / f"{ticker}.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows


def maximum_drawdown(equity_values):
    peak = equity_values[0]
    worst = 0.0
    for value in equity_values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return worst * 100


def simulate(records, price_rows):
    date_to_index = {
        row["date"]: i for i, row in enumerate(price_rows)
    }

    records = sorted(records, key=lambda r: r["forecast_date"])
    first_date = records[0]["forecast_date"]
    last_date = records[-1]["forecast_date"]

    first_index = date_to_index[first_date]
    last_index = date_to_index[last_date]

    capital = INITIAL_CAPITAL
    buy_hold_start = float(price_rows[first_index + 1]["open"])
    buy_hold_end = float(price_rows[min(
        last_index + HORIZON, len(price_rows) - 1
    )]["close"])

    buy_hold_return = (
        buy_hold_end / buy_hold_start
        * (1 - COST_PER_SIDE) ** 2 - 1
    ) * 100

    trades = []
    equity = [capital]
    last_exit_index = -1

    for record in records:
        index = date_to_index.get(record["forecast_date"])
        if index is None:
            continue

        entry_index = index + 1
        exit_index = index + HORIZON

        if entry_index <= last_exit_index:
            continue
        if exit_index >= len(price_rows):
            continue

        predicted = float(record["predicted"])
        base = float(price_rows[index]["close"])

        # Remain in cash for a non-positive forecast.
        if predicted <= base:
            continue

        entry = float(price_rows[entry_index]["open"])
        exit_price = float(price_rows[exit_index]["close"])

        if entry <= 0 or exit_price <= 0:
            continue

        gross_factor = exit_price / entry
        net_factor = gross_factor * (1 - COST_PER_SIDE) ** 2

        capital *= net_factor
        last_exit_index = exit_index

        trade = {
            "entry_date": price_rows[entry_index]["date"],
            "exit_date": price_rows[exit_index]["date"],
            "entry_price": entry,
            "exit_price": exit_price,
            "return_pct": (net_factor - 1) * 100,
            "equity_after": capital
        }
        trades.append(trade)
        equity.append(capital)

    wins = sum(t["return_pct"] > 0 for t in trades)

    return {
        "initial_capital_usd": INITIAL_CAPITAL,
        "ending_capital_usd": round(capital, 2),
        "total_return_pct": round(
            (capital / INITIAL_CAPITAL - 1) * 100, 2
        ),
        "buy_and_hold_return_pct": round(buy_hold_return, 2),
        "trade_count": len(trades),
        "win_rate_pct": round(
            wins / len(trades) * 100, 2
        ) if trades else None,
        "max_closed_trade_drawdown_pct": round(
            maximum_drawdown(equity), 2
        ),
        "trades": trades
    }


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            "Run compare_models_v3.py first"
        )

    grouped = defaultdict(list)

    with INPUT.open(encoding="utf-8-sig", newline="") as f:
        for record in csv.DictReader(f):
            grouped[(record["ticker"], record["model"])].append(
                record
            )

    report = {
        "updated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "assumptions": {
            "initial_capital_usd": INITIAL_CAPITAL,
            "holding_period_sessions": HORIZON,
            "cost_per_side_pct": COST_PER_SIDE * 100,
            "long_only": True,
            "signal_at_close": True,
            "entry_next_open": True,
            "exit_fifth_session_close": True,
            "trade_overlap": False
        },
        "by_ticker": {},
        "notes": [
            "Historical simulation, not actual execution.",
            "Full historical period is used, not independent test.",
            "Prices are historically adjusted.",
            "No taxes, market impact, or overnight liquidity constraints.",
            "Drawdown is measured at closed trades only.",
            "Skipped signals remain in cash.",
            "Buy-and-hold uses a single entry and exit."
        ]
    }

    all_trades = []

    tickers = sorted(set(key[0] for key in grouped))

    for ticker in tickers:
        price_rows = load_prices(ticker)
        report["by_ticker"][ticker] = {}

        for model in MODELS:
            records = grouped.get((ticker, model), [])
            if not records:
                continue

            result = simulate(records, price_rows)
            trades = result.pop("trades")
            report["by_ticker"][ticker][model] = result

            for trade in trades:
                all_trades.append({
                    "ticker": ticker,
                    "model": model,
                    **trade
                })

            print(
                ticker, model,
                "return:", result["total_return_pct"],
                "trades:", result["trade_count"]
            )

    (OUTPUT / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "ticker", "model", "entry_date", "exit_date",
        "entry_price", "exit_price", "return_pct", "equity_after"
    ]

    with (OUTPUT / "trades.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_trades)

    print("Trading simulation completed")


if __name__ == "__main__":
    main()
