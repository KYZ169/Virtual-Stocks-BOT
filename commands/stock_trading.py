# stock_trading.py

import sqlite3
from datetime import datetime, timedelta
import asyncio

DB_PATH = "stock_data.db"

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

# --- 共通関数 ---

def get_all_stock_prices():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT symbol, price FROM stocks ORDER BY symbol ASC")
        return c.fetchall()
    
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

def sell_stock(user_id: str, symbol: str, amount: int, auto: bool = False):
    with get_connection() as conn:
        c = conn.cursor()

        current_price = get_current_price(symbol)
        if current_price is None:
            return "銘柄が存在しません"
        
        # 所有数確認
        if auto:
            c.execute("SELECT SUM(amount) FROM user_stocks WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NOT NULL", (user_id, symbol))
        else:
            c.execute("SELECT SUM(amount) FROM user_stocks WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL", (user_id, symbol))
        total_owned = c.fetchone()[0] or 0

        if amount == 0:
            amount = total_owned

        if total_owned < amount:
            return f"保有数が不足しています（保有: {total_owned} < 要求: {amount}）"

        total_profit_or_loss = 0
        remaining = amount

        # 売却元取得（手動 or 自動）
        if auto:
            c.execute("SELECT rowid, amount, buy_price FROM user_stocks WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NOT NULL ORDER BY rowid ASC", (user_id, symbol))
        else:
            c.execute("SELECT rowid, amount, buy_price FROM user_stocks WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL ORDER BY rowid ASC", (user_id, symbol))
        rows = c.fetchall()

        if not rows:
            return f"{symbol}を売却できる在庫が見つかりませんでした。"
        
        sold_amount = 0

        # 売却処理（古い順）
        for rowid, owned, buy_price in rows:
            if remaining <= 0:
                break

            sell_now = min(owned, remaining)
            revenue = sell_now * current_price
            cost = sell_now * buy_price
            profit_or_loss = revenue - cost
            total_profit_or_loss += profit_or_loss

            # ✅ 還元処理（損失がある場合、stocksごとのadded_by_user_idを参照）
            if profit_or_loss < 0:
                loss = abs(profit_or_loss)
                c.execute("SELECT added_by_user_id FROM stocks WHERE symbol = ?", (symbol,))
                added_by_result = c.fetchone()
                added_by = added_by_result[0] if added_by_result else None

                if added_by and added_by != user_id:
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(loss), added_by))

                # ✅ この位置に置くことでエラーを防げる
                print(f"【DEBUG】損失 {loss}、追加者: {added_by}、売却者: {user_id}")
            else:
                # 損失がなかった場合でも DEBUG を出すならこちら
                print(f"【DEBUG】損失なし、売却者: {user_id}")
                
            # 保有数更新
            if owned == sell_now:
                c.execute("DELETE FROM user_stocks WHERE rowid = ?", (rowid,))
            else:
                c.execute("UPDATE user_stocks SET amount = amount - ? WHERE rowid = ?", (sell_now, rowid))

            remaining -= sell_now
            sold_amount += sell_now

        # 売却益を加算
        total_revenue = current_price * sold_amount
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_revenue, user_id))

        conn.commit()
        return f"{symbol}を {sold_amount}口 売却し {round(total_revenue)}円 を受け取りました。(損益：{round(total_profit_or_loss):+}円)"

# --- 株取引機能 ---

def buy_stock(user_id: str, symbol: str, amount: int, auto_sell_minutes: int = 0):
    with get_connection() as conn:
        c = conn.cursor()

        price = get_current_price(symbol)
        if price is None:
            return "銘柄が存在しません"

        total_cost = round(price * amount)
        balance = get_balance(user_id)
        if balance < total_cost:
            return f"残高不足（必要: {total_cost}）"

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
        return f"{symbol} を 1口 {price}円で{amount}口 購入しました（合計{price * amount}円）"

def get_all_current_prices_message():
    rows = get_all_stock_prices()
    if not rows:
        return "📉 現在、登録されている銘柄がありません。"
    msg = "💹 **現在の全銘柄価格**\n"
    for symbol, price in rows:
        msg += f"・{symbol}: {price:.0f} 円\n"
    return msg

async def sell_stock_async(user_id: str, symbol: str, amount: int):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sell_stock, user_id, symbol, amount, True)
