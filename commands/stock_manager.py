import sqlite3
import random
import time
from datetime import datetime
from discord.ext import tasks

DB_PATH = "stock_data.db"

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                symbol TEXT PRIMARY KEY,
                price INTEGER,
                speed INTEGER,
                min_fluct INTEGER,
                max_fluct INTEGER,
                channel_id TEXT,
                added_by_user_id TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS stock_history (
                symbol TEXT,
                timestamp DATETIME,
                price INTEGER,
                delta INTEGER
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                balance INTEGER
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_stocks (
                user_id TEXT,
                symbol TEXT,
                amount INTEGER,
                buy_price INTEGER,
                auto_sell_time TIMESTAMP
            )
        """)

        conn.commit()

def get_all_prices():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT symbol, price FROM stocks")
        return c.fetchall()

# キャッシュとして保持
last_update_times = {}

def random_update_prices():
    now = time.time()
    
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT symbol, price, speed, min_fluct, max_fluct FROM stocks")
        stocks = c.fetchall()

        for symbol, price, speed, min_f, max_f in stocks:
            # speedは「何分おきに更新するか」
            last_time = last_update_times.get(symbol)
            if last_time is not None and now - last_time < speed:
                continue  # 更新間隔に満たない

            fluct = random.uniform(min_f, max_f)
            direction = random.choice([-1, 1])
            delta = int(fluct * direction)
            new_price = max(1, price + delta)

            c.execute("UPDATE stocks SET price = ? WHERE symbol = ?", (new_price, symbol))
            last_update_times[symbol] = now  # 最終更新時刻を記録

        conn.commit()

def log_current_prices():
    with get_connection() as conn:
        c = conn.cursor()
        now = datetime.now().replace(microsecond=0)

        # 現在の価格、チャンネルIDを取得
        c.execute("SELECT symbol, price, channel_id FROM stocks")
        stock_rows = c.fetchall()

        # 各symbolの前回価格を取得して差分計算
        prev_prices = {}
        for row in stock_rows:
            symbol = row[0]
            c.execute("""SELECT price FROM stock_history 
                         WHERE symbol = ? 
                         ORDER BY timestamp DESC LIMIT 1""", (symbol,))
            fetched = c.fetchone()
            prev_prices[symbol] = fetched[0] if fetched else None

        updates = []

        for symbol, current_price, channel_id in stock_rows:
            prev_price = prev_prices.get(symbol)
            if prev_price is not None and current_price == prev_price:
                continue

            delta = current_price - prev_price if prev_price is not None else 0

            # 履歴に保存
            c.execute("""
                INSERT INTO stock_history (symbol, timestamp, price, delta)
                VALUES (?, ?, ?, ?)
            """, (symbol, now, current_price, delta))

            # チャンネル通知メッセージ作成
            if channel_id:
                message = f"`{symbol}` の現在価格: `{current_price}`円（前回比: {delta:+}円）"
                updates.append((int(channel_id), message))

        conn.commit()
        return updates


def cleanup_old_history(limit: int = 100):
    with get_connection() as conn:
        c = conn.cursor()

        # 対象となる銘柄一覧を取得
        c.execute("SELECT DISTINCT symbol FROM stock_history")
        symbols = [row[0] for row in c.fetchall()]

        for symbol in symbols:
            # 現在の履歴数を確認
            c.execute("SELECT COUNT(*) FROM stock_history WHERE symbol = ?", (symbol,))
            count = c.fetchone()[0]

            # 履歴が limit を超える場合、古いデータを削除
            if count > limit:
                delete_count = count - limit
                c.execute("""
                    DELETE FROM stock_history
                    WHERE rowid IN (
                        SELECT rowid FROM stock_history
                        WHERE symbol = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                """, (symbol, delete_count))

        conn.commit()
 
def add_stock(symbol, price, speed, min_fluct, max_fluct, channel_id, added_by_user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO stocks 
            (symbol, price, speed, min_fluct, max_fluct, channel_id, added_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, price, speed, min_fluct, max_fluct, channel_id, added_by_user_id))
        conn.commit()

def delete_stock(symbol):
    with get_connection() as conn:
        conn.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
        conn.execute("DELETE FROM user_stocks WHERE symbol = ?", (symbol,))
        conn.execute("DELETE FROM stock_history WHERE symbol = ?", (symbol,))

def get_price(symbol):
    with get_connection() as conn:
        cur = conn.execute("SELECT price FROM stocks WHERE symbol = ?", (symbol,))
        result = cur.fetchone()
        return result[0] if result else None