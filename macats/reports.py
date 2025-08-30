# macats/reports.py
import os, math, csv, time
import pandas as pd
import matplotlib.pyplot as plt

LOG_DIR = "logs"
TRADES_CSV = os.path.join(LOG_DIR, "trades.csv")
EQUITY_CSV = os.path.join(LOG_DIR, "equity.csv")
PLOT_PNG = os.path.join(LOG_DIR, "equity_curve.png")

def load_logs():
    trades = pd.read_csv(TRADES_CSV) if os.path.exists(TRADES_CSV) else pd.DataFrame()
    equity = pd.read_csv(EQUITY_CSV) if os.path.exists(EQUITY_CSV) else pd.DataFrame()
    if "ts" in trades: trades["ts"] = pd.to_datetime(trades["ts"], unit="s")
    if "ts" in equity: equity["ts"] = pd.to_datetime(equity["ts"], unit="s")
    return trades, equity

def compute_stats(trades: pd.DataFrame, equity: pd.DataFrame):
    stats = {}
    if not equity.empty:
        equity = equity.sort_values("ts")
        stats["final_equity"] = float(equity["equity"].iloc[-1])
        stats["max_drawdown"] = float((equity["equity"]/equity["equity"].cummax()-1).min())
        ret = equity["equity"].pct_change().fillna(0.0)
        if len(ret) > 1:
            stats["sharpe_like"] = float((ret.mean() / (ret.std()+1e-9)) * (len(ret)**0.5))
    if not trades.empty:
        # infer closed trades by sign flips / flatten fills
        # here we approximate each non-flat fill as a trade outcome by delta in realized
        wins = 0; losses = 0; pnl_list = []
        last_realized = None
        for _, r in trades.iterrows():
            realized = float(r.get("realized_after",0.0))
            if last_realized is not None:
                delta = realized - last_realized
                if abs(delta) > 1e-9:
                    pnl_list.append(delta)
                    if delta > 0: wins += 1
                    else: losses += 1
            last_realized = realized
        if pnl_list:
            stats["trades"] = len(pnl_list)
            stats["win_rate"] = wins / len(pnl_list)
            stats["avg_profit"] = sum(pnl_list)/len(pnl_list)
            stats["median_profit"] = float(pd.Series(pnl_list).median())
    return stats

def plot_equity(equity: pd.DataFrame, out=PLOT_PNG):
    if equity.empty:
        print("No equity data to plot.")
        return
    equity = equity.sort_values("ts")
    plt.figure(figsize=(9,4.5))
    plt.plot(equity["ts"], equity["equity"])
    plt.title("Equity Curve (Paper)")
    plt.xlabel("Time"); plt.ylabel("Equity")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print(f"Saved {out}")

if __name__ == "__main__":
    trades, equity = load_logs()
    stats = compute_stats(trades, equity)
    print("=== STATS ===")
    for k,v in stats.items():
        if "rate" in k or "drawdown" in k:
            print(f"{k}: {v:.2%}")
        else:
            print(f"{k}: {v}")
    plot_equity(equity)