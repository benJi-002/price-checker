import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Product:
    id: int
    name: str
    url: str
    last_price: Optional[float]
    notify_on_any_change: int
    notify_below_price: Optional[float]
    is_active: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DB:
    def __init__(self, path: str):
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                last_price REAL,
                notify_on_any_change INTEGER NOT NULL DEFAULT 1,
                notify_below_price REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                old_price REAL,
                new_price REAL NOT NULL,
                reason TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            """)
            conn.commit()

    def add_product(self, name: str, url: str, threshold: Optional[float]) -> None:
        now = utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO products (name, url, last_price, notify_on_any_change, notify_below_price, is_active, created_at, updated_at)
                VALUES (?, ?, NULL, 1, ?, 1, ?, ?)
                """,
                (name, url, threshold, now, now),
            )
            conn.commit()

    def list_active_products(self) -> list[Product]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM products WHERE is_active=1 ORDER BY id").fetchall()
        return [
            Product(
                id=r["id"],
                name=r["name"],
                url=r["url"],
                last_price=r["last_price"],
                notify_on_any_change=r["notify_on_any_change"],
                notify_below_price=r["notify_below_price"],
                is_active=r["is_active"],
            )
            for r in rows
        ]

    def set_active(self, product_id: int, active: bool) -> None:
        now = utc_now_iso()
        with self._conn() as conn:
            conn.execute("UPDATE products SET is_active=?, updated_at=? WHERE id=?",
                         (1 if active else 0, now, product_id))
            conn.commit()

    def insert_price_history(self, product_id: int, price: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO price_history (product_id, price, fetched_at) VALUES (?, ?, ?)",
                (product_id, price, utc_now_iso()),
            )
            conn.commit()

    def update_last_price(self, product_id: int, price: float) -> None:
        now = utc_now_iso()
        with self._conn() as conn:
            conn.execute("UPDATE products SET last_price=?, updated_at=? WHERE id=?",
                         (price, now, product_id))
            conn.commit()

    def insert_notification(self, product_id: int, old_price: Optional[float], new_price: float, reason: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO notifications (product_id, old_price, new_price, reason, sent_at) VALUES (?, ?, ?, ?, ?)",
                (product_id, old_price, new_price, reason, utc_now_iso()),
            )
            conn.commit()