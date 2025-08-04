# stock_trading.py

import sqlite3
from datetime import datetime, timedelta
import asyncio

DB_PATH = "stock_data.db"

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

# --- 共通関数 ---

def get_current_price(symbol: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT price FROM stocks WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        return row[0] if row else None

def update_balance(user_id: str, amount: float):
    with get_connection() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

def get_balance(user_id: str):
    with get_connection() as conn:
        cur = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0.0

def init_user(user_id: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0.0))

def get_user_manual_stocks(user_id: str, symbol: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT amount, buy_price FROM user_stocks
            WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL
        """, (user_id, symbol))
        return c.fetchall()
    
def get_user_holdings(user_id: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT symbol, SUM(amount) FROM user_stocks
            WHERE user_id = ?
            GROUP BY symbol
        """, (user_id,))
        return c.fetchall()

# --- 株取引機能 ---

def buy_stock(user_id: str, symbol: str, amount: int, auto_sell_minutes: int = 0):
    with get_connection() as conn:
        c = conn.cursor()

        price = get_current_price(symbol)
        if price is None:
            return False, "銘柄が存在しません"

        total_cost = round(price * amount)
        balance = get_balance(user_id)
        if balance < total_cost:
            return False, f"残高不足（必要: {total_cost}）"

        # 残高減算
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, user_id))

        auto_sell_time = (
            (datetime.now() + timedelta(minutes=auto_sell_minutes)).isoformat()
            if auto_sell_minutes > 0 else None
        )

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_stocks (
                user_id TEXT,
                symbol TEXT,
                amount INTEGER,
                buy_price REAL,
                auto_sell_time TIMESTAMP
            )
        """)
        c.execute("""
            INSERT INTO user_stocks (user_id, symbol, amount, buy_price, auto_sell_time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, symbol, amount, price, auto_sell_time))

        conn.commit()
        return True, f"{symbol} を 1口 {price}円で{amount}口 購入しました（合計{price * amount}円）"

async def sell_stock(user_id: str, symbol: str, amount: int) -> str:
    price = get_current_price(symbol)
    if price is None:
        return f"❌ 銘柄 `{symbol}` が存在しません"

    holdings = get_user_manual_stocks(user_id, symbol)
    if not holdings:
        return f"❌ `{symbol}` の保有がありません"

    total_amount = sum(row[0] for row in holdings)
    if amount > total_amount:
        return f"❌ 保有口数（{total_amount}口）未満しか売却できません"

    remaining = amount
    with get_connection() as conn:
        c = conn.cursor()

        # まず該当行を取得（rowid付きで）
        c.execute("""
            SELECT rowid, amount FROM user_stocks
            WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL
            ORDER BY rowid ASC
        """, (user_id, symbol))
        rows = c.fetchall()

        for rowid, held_amount in rows:
            if remaining <= 0:
                break

            sell_amount = min(held_amount, remaining)
            new_amount = held_amount - sell_amount

            if new_amount > 0:
                c.execute("UPDATE user_stocks SET amount = ? WHERE rowid = ?", (new_amount, rowid))
            else:
                c.execute("DELETE FROM user_stocks WHERE rowid = ?", (rowid,))
            
            remaining -= sell_amount

        # 売却金額の加算
        value = round(price * amount)
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (value, user_id))
        conn.commit()

    return f"💴 `{symbol}` を {amount}口 売却し {value}円 を受け取りました。"
    
async def auto_sell_loop(client):
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(30)
        now = datetime.now().isoformat()

        with get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT user_id, symbol, amount FROM user_stocks
                WHERE auto_sell_time IS NOT NULL AND auto_sell_time <= ?
            """, (now,))
            rows = c.fetchall()

            for user_id, symbol, amount in rows:
                price = get_current_price(symbol)
                if price:
                    value = round(price * amount)
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (value, user_id))

                    try:
                        user = await client.fetch_user(int(user_id))
                        await user.send(f"💸 {symbol} を {amount}口 売却し {value}円を取得しました")
                    except Exception as e:
                        print(f"❌ DM送信エラー: {e}")

            c.execute("DELETE FROM user_stocks WHERE auto_sell_time IS NOT NULL AND auto_sell_time <= ?", (now,))
            conn.commit()

