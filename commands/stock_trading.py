import sqlite3
import os
from datetime import datetime, timedelta
import asyncio

# 絶対パスに変換し、sharedフォルダを自動作成
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "..", "..", "shared")
os.makedirs(DB_DIR, exist_ok=True)  # ← 重要: sharedディレクトリがなければ作る

DB_PATH = os.path.join(DB_DIR, "shared.db")

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

# --- 共通関数 ---

def get_all_stock_prices():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT symbol, price FROM stocks ORDER BY symbol ASC")
        return c.fetchall()
    
def get_current_price(symbol: str) -> int | None:
    symbol = symbol.upper()
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT price FROM stocks WHERE symbol = ?", (symbol,))
        row = c.fetchone()
        return row[0] if row else None

def update_balance(user_id: str, amount: float):
    with get_connection() as conn:
        conn.execute("UPDATE balances SET balance = balance + ? WHERE user_id = ? AND currency = 'VETY'", (amount, user_id))

def get_balance(user_id: str):
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT balance FROM balances WHERE user_id = ? AND currency = 'VETY'",
            (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else 0.0

def init_user(user_id: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO balances(user_id, balance) VALUES (?, ?)", (user_id, 0.0))

def get_user_manual_stocks(user_id: str, symbol: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT amount, buy_price FROM user_stocks
            WHERE user_id = ? AND currency = 'VETY'","AND symbol = ? AND auto_sell_time IS NULL
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
            return {
                "ok": False,
                "message": "銘柄が存在しません",
                "symbol": symbol,
                "amount": 0,
                "unit_price": None,
                "total": None,
                "profit_loss": None,
            }

        # 所有数確認（既存のまま）
        if auto:
            c.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM user_stocks "
                "WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NOT NULL",
                (user_id, symbol)
            )
        else:
            c.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM user_stocks "
                "WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL",
                (user_id, symbol)
            )
        total_owned = c.fetchone()[0] or 0

        if amount == 0:
            amount = total_owned

        if total_owned < amount:
            return {
                "ok": False,
                "message": f"保有数が不足しています（保有: {total_owned} < 要求: {amount}）",
                "symbol": symbol,
                "amount": 0,
                "unit_price": current_price,
                "total": 0,
                "profit_loss": 0,
            }

        total_profit_or_loss = 0
        remaining = amount
        sold_amount = 0

        # 売却元取得（既存のまま）
        if auto:
            c.execute(
                "SELECT rowid, amount, buy_price FROM user_stocks "
                "WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NOT NULL "
                "ORDER BY rowid ASC",
                (user_id, symbol)
            )
        else:
            c.execute(
                "SELECT rowid, amount, buy_price FROM user_stocks "
                "WHERE user_id = ? AND symbol = ? AND auto_sell_time IS NULL "
                "ORDER BY rowid ASC",
                (user_id, symbol)
            )
        rows = c.fetchall()

        if not rows:
            return {
                "ok": False,
                "message": f"{symbol}を売却できる在庫が見つかりませんでした。",
                "symbol": symbol,
                "amount": 0,
                "unit_price": current_price,
                "total": 0,
                "profit_loss": 0,
            }

        # 売却処理（古い順）
        for rowid, owned, buy_price in rows:
            if remaining <= 0:
                break

            sell_now = min(owned, remaining)
            revenue = sell_now * current_price
            cost = sell_now * buy_price
            profit_or_loss = revenue - cost
            total_profit_or_loss += profit_or_loss

            # 還元処理（既存）
            if profit_or_loss < 0:
                loss = abs(profit_or_loss)
                c.execute("SELECT added_by_user_id FROM stocks WHERE symbol = ?", (symbol,))
                added_by_result = c.fetchone()
                added_by = added_by_result[0] if added_by_result else None

                if added_by and added_by != user_id:
                    # ▼ 通貨指定（VETY）を明示（重要）
                    c.execute("""
                        INSERT OR IGNORE INTO balances(user_id, currency, balance)
                        VALUES (?, 'VETY', 0)
                    """, (added_by,))
                    c.execute("""
                        UPDATE balances SET balance = balance + ?
                        WHERE user_id = ? AND currency = 'VETY'
                    """, (int(loss), added_by))

            # 保有数更新（既存）
            if owned == sell_now:
                c.execute("DELETE FROM user_stocks WHERE rowid = ?", (rowid,))
            else:
                c.execute("UPDATE user_stocks SET amount = amount - ? WHERE rowid = ?", (sell_now, rowid))

            remaining -= sell_now
            sold_amount += sell_now

        # 売却益を加算（VETYに入れる）
        total_revenue = current_price * sold_amount
        c.execute("""
            INSERT OR IGNORE INTO balances(user_id, currency, balance)
            VALUES (?, 'VETY', 0)
        """, (user_id,))
        c.execute("""
            UPDATE balances SET balance = balance + ?
            WHERE user_id = ? AND currency = 'VETY'
        """, (int(total_revenue), user_id))

        conn.commit()

        msg = f"{symbol}を {sold_amount}口 売却し {round(total_revenue)} Vety を受け取りました。(損益：{round(total_profit_or_loss):+} Vety)"
        return {
            "ok": True,
            "message": msg,
            "symbol": symbol,
            "amount": sold_amount,
            "unit_price": current_price,
            "total": int(round(total_revenue)),
            "profit_loss": int(round(total_profit_or_loss)),
        }
# --- 株取引機能 ---

def buy_stock(user_id: str, symbol: str, amount: int, auto_sell_minutes: int = 0):
    if amount <= 0:
        return "購入数は1以上を指定してください。"

    with get_connection() as conn:
        c = conn.cursor()

        price = get_current_price(symbol)
        if price is None:
            return "銘柄が存在しません"

        total_cost = int(round(price * amount))
        balance = get_balance(user_id)
        if balance < total_cost:
            return f"残高不足（必要: {total_cost} Vety / 現在: {balance} Vety）"

        # 残高減算（★スペースとバインド修正）
        c.execute(
            "UPDATE balances SET balance = balance - ? WHERE user_id = ? AND currency = 'VETY'",
            (total_cost, user_id)
        )

        # 念のため、対象行がなければエラー返す（init_userが確実なら不要）
        if c.rowcount == 0:
            conn.rollback()
            return "残高レコードが見つかりません（初期化が必要かも）。"

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
                auto_sell_time TEXT
            )
        """)  # auto_sell_time は ISO文字列で保存

        c.execute("""
            INSERT INTO user_stocks (user_id, symbol, amount, buy_price, auto_sell_time)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, symbol.upper(), amount, float(price), auto_sell_time))
        
        conn.commit()
        return f"{symbol} を 1口 {price}Vetyで{amount}口 購入しました（合計{price * amount}Vety）"

def get_all_current_prices_message():
    rows = get_all_stock_prices()
    if not rows:
        return "📉 現在、登録されている銘柄がありません。"
    msg = "💹 **現在の全銘柄価格**\n"
    for symbol, price in rows:
        msg += f"・{symbol}: {price:.0f} Vety\n"
    return msg

# 非同期ラッパー：同期のsell_stockを非同期で使えるようにする
async def sell_stock_async(user_id: str, symbol: str, amount: int, auto: bool = False):
    loop = asyncio.get_running_loop()
    # sell_stock が dict を返す想定に変更
    return await loop.run_in_executor(None, sell_stock, user_id, symbol, amount, auto)