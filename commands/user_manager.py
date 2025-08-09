import sqlite3
import os

# 絶対パスに変換し、sharedフォルダを自動作成
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "..", "..", "shared")
os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = os.path.join(DB_DIR, "shared.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    # ある程度同時アクセスに強くする
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_user(user_id: str):
    """VETYの行が無ければ0で作る"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                user_id TEXT,
                currency TEXT,
                balance REAL DEFAULT 0,
                PRIMARY KEY (user_id, currency)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO balances(user_id, currency, balance)
            VALUES (?, 'VETY', 0)
        """, (user_id,))

def get_balance(user_id: str) -> float:
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT balance FROM balances
            WHERE user_id = ? AND currency = 'VETY'
        """, (user_id,))
        row = c.fetchone()
        return row[0] if row else 0.0

def add_balance(user_id: str, amount: float):
    amount = float(amount)
    if amount <= 0:
        return
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO balances(user_id, currency, balance)
            VALUES (?, 'VETY', 0)
        """, (user_id,))
        c.execute("""
            UPDATE balances
            SET balance = balance + ?
            WHERE user_id = ?
        """, (amount, user_id))

def decrease_balance(user_id: str, amount: float, currency: str = "VETY") -> bool:
    amount = float(amount)
    if amount <= 0:
        return False

    cur = currency.upper()

    with get_connection() as conn:
        c = conn.cursor()

        # 口座が無ければ 0 で作成
        c.execute("""
            INSERT OR IGNORE INTO balances (user_id, currency, balance)
            VALUES (?, ?, 0)
        """, (user_id, cur))

        # 残高が十分な時だけ原子的に減額
        c.execute("""
            UPDATE balances
               SET balance = balance - ?
             WHERE user_id = ?
               AND UPPER(currency) = UPPER(?)
               AND balance >= ?
        """, (amount, user_id, cur, amount))

        ok = (c.rowcount == 1)
        conn.commit()
        return ok
    
def _normalize_balance_row(conn, user_id: str, currency: str) -> None:
    cur = currency.upper()
    c = conn.cursor()
    # 大小混在の合計を作る
    c.execute("""
        SELECT COALESCE(SUM(balance), 0)
        FROM balances
        WHERE user_id = ? AND UPPER(currency) = UPPER(?)
    """, (user_id, cur))
    total = c.fetchone()[0] or 0

    # 既存の大小混在行を全部消して、1行だけ入れ直す
    c.execute("DELETE FROM balances WHERE user_id = ? AND UPPER(currency) = UPPER(?)",
              (user_id, cur))
    c.execute("""
        INSERT INTO balances (user_id, currency, balance)
        VALUES (?, ?, ?)
    """, (user_id, cur, total))

def transfer_balance(from_user_id: str, to_user_id: str, amount: float, currency: str = "VETY") -> bool:
    amount = float(amount)
    if amount <= 0 or from_user_id == to_user_id:
        return False

    cur = currency.upper()
    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute("BEGIN")

            # まず両者の通貨行を正規化（重複行を1行に統合）
            _normalize_balance_row(conn, from_user_id, cur)
            _normalize_balance_row(conn, to_user_id, cur)

            # 送金元の残高確認（合計で確認）
            c.execute("""
                SELECT balance FROM balances
                WHERE user_id = ? AND currency = ?
                LIMIT 1
            """, (from_user_id, cur))
            row = c.fetchone()
            bal = row[0] if row else 0
            if bal < amount:
                conn.rollback()
                return False

            # 減額（原子的）
            c.execute("""
                UPDATE balances
                   SET balance = balance - ?
                 WHERE user_id = ? AND currency = ? AND balance >= ?
            """, (amount, from_user_id, cur, amount))
            if c.rowcount != 1:
                conn.rollback()
                return False

            # 加算
            c.execute("""
                UPDATE balances
                   SET balance = balance + ?
                 WHERE user_id = ? AND currency = ?
            """, (amount, to_user_id, cur))
            if c.rowcount != 1:
                conn.rollback()
                return False

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False

def log_issuance(issued_by: str, issued_to: str, amount: float):
    pass
