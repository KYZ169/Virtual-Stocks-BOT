import sqlite3

DB_PATH = "stock_data.db"

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10)

def init_user(user_id: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                balance REAL DEFAULT 0
            )
        """)
        c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()

def get_balance(user_id: str) -> float:
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        return result[0] if result else 0

def add_balance(user_id: str, amount: float):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def log_issuance(issued_by: str, issued_to: str, amount: float):
    # オプション機能: 発行履歴のロギング
    pass  # 必要に応じてDBに記録する機能を追加
