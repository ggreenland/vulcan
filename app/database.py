import aiosqlite
import secrets
from datetime import datetime, timedelta
from typing import Optional
import bcrypt

from app.config import config

DATABASE_PATH = config.DATABASE_PATH


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        await db.commit()


async def get_or_create_user(email: str, name: str, picture: str) -> dict:
    """Get existing user or create new one."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = await cursor.fetchone()

        now = datetime.utcnow().isoformat()

        if user:
            await db.execute(
                "UPDATE users SET last_login = ?, name = ?, picture = ? WHERE id = ?",
                (now, name, picture, user["id"]),
            )
            await db.commit()
            return dict(user)
        else:
            cursor = await db.execute(
                "INSERT INTO users (email, name, picture, created_at, last_login) VALUES (?, ?, ?, ?, ?)",
                (email, name, picture, now, now),
            )
            await db.commit()
            return {
                "id": cursor.lastrowid,
                "email": email,
                "name": name,
                "picture": picture,
                "created_at": now,
                "last_login": now,
            }


async def create_session(user_id: int, expires_hours: int = 168) -> str:
    """Create a new session for a user. Default expiry is 7 days."""
    session_id = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=expires_hours)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now.isoformat(), expires_at.isoformat()),
        )
        await db.commit()

    return session_id


async def get_session(session_id: str) -> Optional[dict]:
    """Get session if valid and not expired."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, u.email, u.name, u.picture
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            """,
            (session_id,),
        )
        session = await cursor.fetchone()

        if session:
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.utcnow() < expires_at:
                return dict(session)
            else:
                await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                await db.commit()

    return None


async def delete_session(session_id: str):
    """Delete a session."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()


async def create_api_key(user_id: int, name: str) -> tuple[int, str]:
    """Create a new API key. Returns (key_id, raw_key)."""
    raw_key = secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    key_prefix = raw_key[:8]
    now = datetime.utcnow().isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO api_keys (user_id, name, key_hash, key_prefix, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, key_hash, key_prefix, now),
        )
        await db.commit()
        return cursor.lastrowid, raw_key


async def validate_api_key(raw_key: str) -> Optional[dict]:
    """Validate an API key and return user info if valid."""
    key_prefix = raw_key[:8]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT ak.*, u.email, u.name
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.key_prefix = ?
            """,
            (key_prefix,),
        )
        keys = await cursor.fetchall()

        for key in keys:
            if bcrypt.checkpw(raw_key.encode(), key["key_hash"].encode()):
                await db.execute(
                    "UPDATE api_keys SET last_used = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), key["id"]),
                )
                await db.commit()
                return dict(key)

    return None


async def get_user_api_keys(user_id: int) -> list[dict]:
    """Get all API keys for a user (without hashes)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, key_prefix, created_at, last_used FROM api_keys WHERE user_id = ?",
            (user_id,),
        )
        keys = await cursor.fetchall()
        return [dict(k) for k in keys]


async def delete_api_key(key_id: int, user_id: int) -> bool:
    """Delete an API key. Returns True if deleted."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0
