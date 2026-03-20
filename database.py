import aiosqlite
import datetime

DB_PATH = "vpn_bot.db"

# ---------- INIT ----------

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                outline_key_id TEXT,
                expire_at DATETIME,
                trial_used BOOLEAN DEFAULT 0
            )
        """)

        # Таблица устройств
        await db.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                device_name TEXT
            )
        """)

        # Таблица конфига/ключей (если нужно)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.commit()

# ---------- DEVICES ----------

async def add_device(user_id, device_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO devices (user_id, device_name) VALUES (?, ?)",
            (user_id, device_name)
        )
        await db.commit()

async def device_count(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM devices WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0]

# ---------- TRIAL ----------

async def is_trial_used(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT trial_used FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] == 1 if row else False

async def set_trial_used(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, trial_used)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET trial_used=1
        """, (user_id,))
        await db.commit()

# ---------- VPN (OUTLINE) ----------

async def activate_user(user_id, key_id, expire_at):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, outline_key_id, expire_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                outline_key_id=excluded.outline_key_id,
                expire_at=excluded.expire_at
        """, (user_id, key_id, expire_at))
        await db.commit()

async def get_user_key(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT outline_key_id, expire_at FROM users WHERE user_id=?",
            (user_id,)
        )
        return await cursor.fetchone()

async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, outline_key_id
            FROM users
            WHERE expire_at > ?
        """, (datetime.datetime.now(),))
        return await cursor.fetchall()

async def get_expired_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, outline_key_id
            FROM users
            WHERE expire_at <= ?
        """, (datetime.datetime.now(),))
        return await cursor.fetchall()

# ---------- DELETE USER ----------

async def delete_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM users WHERE user_id=?",
            (user_id,)
        )
        await db.commit()