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
                max_fluct INTEGER
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
        
        # 現在の価格を取得
        c.execute("SELECT symbol, price FROM stocks")
        current_prices = dict(c.fetchall())

        # 各symbolの直前価格を一括取得
        prev_prices = {}
        for symbol in current_prices.keys():
            c.execute("""
                SELECT price FROM stock_history 
                WHERE symbol = ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (symbol,))
            row = c.fetchone()
            prev_prices[symbol] = row[0] if row else None

        # すべて挿入（全て同じ now でOK）
        for symbol, current_price in current_prices.items():
            prev_price = prev_prices[symbol]
            if prev_price is not None and current_price == prev_price:
                continue  

            delta = round(current_price - prev_price) if prev_price is not None else None

            c.execute("""
                INSERT INTO stock_history (symbol, timestamp, price, delta)
                VALUES (?, ?, ?, ?)
            """, (symbol, now, current_price, delta))

        conn.commit()

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
 
def add_stock(symbol, price, speed, min_fluct, max_fluct):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO stocks (symbol, price, speed, min_fluct, max_fluct)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, price, speed, min_fluct, max_fluct))

def delete_stock(symbol):
    with get_connection() as conn:
        conn.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))

def get_price(symbol):
    with get_connection() as conn:
        cur = conn.execute("SELECT price FROM stocks WHERE symbol = ?", (symbol,))
        result = cur.fetchone()
        return result[0] if result else None

@tasks.loop(seconds=1)
async def auto_update_prices():
    random_update_prices()
    log_current_prices()
    cleanup_old_history()