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

def decrease_balance(user_id: str, amount: float) -> bool:
    amount = float(amount)
    if amount <= 0:
        return False
    with get_connection() as conn:
        c = conn.cursor()
        # 残高が十分なときだけ減額（原子的）
        c.execute("""
            UPDATE balances
            SET balance = balance - ?
            WHERE user_id = ?
        """, (amount, user_id, amount))
        return c.rowcount == 1

def transfer_balance(from_user_id: str, to_user_id: str, amount: float) -> bool:
    amount = float(amount)
    if amount <= 0:
        return False
    with get_connection() as conn:
        c = conn.cursor()
        # 受け取り側の行を用意
        c.execute("""
            INSERT OR IGNORE INTO balances(user_id, currency, balance)
            VALUES (?, 'VETY', 0)
        """, (to_user_id,))
        # 送金元から原子的に減額（残高チェック込み）
        c.execute("""
            UPDATE balances
            SET balance = balance - ?
            WHERE user_id = ?
        """, (amount, from_user_id, amount))
        if c.rowcount != 1:
            return False
        # 受け取り側に加算
        c.execute("""
            UPDATE balances
            SET balance = balance + ?
            WHERE user_id = ?
        """, (amount, to_user_id))
        return True

def log_issuance(issued_by: str, issued_to: str, amount: float):
    pass
