import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sqlite3
from datetime import datetime
import os

DB_PATH = "stock_data.db"

def generate_stock_graph(symbol: str, filename: str) -> bool:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    # text/整数どちらでも拾えるようにしつつ、明らかなゴミは弾く
    c.execute(
        """
        SELECT timestamp, price
        FROM stock_history
        WHERE symbol = ?
          AND timestamp IS NOT NULL
          AND timestamp != ''
        ORDER BY timestamp ASC
        LIMIT 300
        """,
        (symbol,),
    )
    rows = c.fetchall()
    conn.close()

    # 安全にパース
    times, prices = [], []
    for ts, price in rows:
        dt = _to_dt(ts)
        if dt is None:
            continue
        times.append(dt)
        prices.append(price)

    if not times:
        return False

    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(times, prices, marker="o", linewidth=2.0, markersize=4)

    # 最大・最小マーカー
    max_price = max(prices)
    min_price = min(prices)
    ax.plot(times[prices.index(max_price)], max_price, marker="o", color="green", markersize=7)
    ax.plot(times[prices.index(min_price)], min_price, marker="o", color="red", markersize=7)

    ax.set_title(f"{symbol} 株価推移")
    ax.set_xlabel("日時")
    ax.set_ylabel("価格")
    ax.grid(True)
    fig.autofmt_xdate()

    os.makedirs("graphs", exist_ok=True)
    full_path = os.path.join("graphs", filename)
    plt.tight_layout()
    plt.savefig(full_path)
    plt.close()
    return os.path.exists(full_path)
