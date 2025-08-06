import matplotlib.pyplot as plt
import sqlite3
import datetime
import os
from matplotlib import font_manager, rc
font_path = "C:/Windows/Fonts/YuGothR.ttc"  # または "meiryo.ttc", "msgothic.ttc" など
font_prop = font_manager.FontProperties(fname=font_path)
rc('font', family=font_prop.get_name())

DB_PATH = "stock_data.db"

def generate_stock_graph(symbol: str, filename: str) -> bool:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, price FROM stock_history
        WHERE symbol = ?
        ORDER BY timestamp ASC
        LIMIT 100
    """, (symbol,))
    data = c.fetchall()
    conn.close()

    if not data:
        return False

    times = [datetime.datetime.fromisoformat(row[0]) for row in data]
    prices = [row[1] for row in data]

    plt.style.use('default')
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(times, prices, marker='o', color='#007bff', linewidth=2.5, markersize=5)

    # 最大・最小マーカー
    max_price = max(prices)
    min_price = min(prices)
    ax.plot(times[prices.index(max_price)], max_price, marker='o', color='green', markersize=8)
    ax.plot(times[prices.index(min_price)], min_price, marker='o', color='red', markersize=8)

    ax.set_title(f'{symbol} 株価推移')
    ax.set_xlabel('日時')
    ax.set_ylabel('価格')

    ax.grid(True)
    fig.autofmt_xdate()

    # ✅ 保存先フォルダ作成 + 出力ファイルパス作成
    output_dir = "graphs"
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, filename)

    plt.tight_layout()
    plt.savefig(full_path)
    plt.close()
    return os.path.exists(full_path)