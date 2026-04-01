import asyncio
import datetime
import subprocess
import time
import os
import requests

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
import aiosqlite

from database import (
    init_db,
    activate_user,
    get_active_users,
    get_expired_users,
    add_device,
    device_count,
    is_trial_used,
    set_trial_used,
    get_user_key,
    delete_user
)

# ================== НАСТРОЙКИ ==================

MAX_DEVICES = 3

TOKEN = "8721184222:AAHHIy2r7Qf3hI7zXMEwbw8VmGQVJlmS7u0"
ADMIN_IDS = [8272466558]

bot = Bot(token=TOKEN)
dp = Dispatcher()

pending_payments = {}
DB_PATH = "vpn_bot.db"

CONFIGS_DIR = "configs"
used_configs = {}

requests.packages.urllib3.disable_warnings()
OUTLINE_API_URL = "https://77.239.105.246:26387/dmOZJUA13_ALsW1fwiCgPg"
# ================== КНОПКИ ==================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Приобрести подписку", callback_data="tariffs")],
        [
            InlineKeyboardButton(text="🎁 Пробная подписка", callback_data="trial"),
            InlineKeyboardButton(text="📲 Мой VPN", callback_data="myvpn")
        ],
        [
            InlineKeyboardButton(text="🛟 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/outlinesvpnotzyv")
        ],
        [InlineKeyboardButton(text="📲 Как подключить VPN", callback_data="how_to_connect")]
    ])

def tariffs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 мес — 100р", callback_data="tariff_1"),
            InlineKeyboardButton(text="3 мес — 200р", callback_data="tariff_3")
        ],
        [
            InlineKeyboardButton(text="6 мес — 400р", callback_data="tariff_6"),
            InlineKeyboardButton(text="12 мес — 800р", callback_data="tariff_12")
        ],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
# ================== MYVPN ==================

@dp.callback_query(lambda c: c.data == "myvpn")
async def myvpn(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT outline_key_id, expire_at FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

    if not row:
        await callback.message.answer("❌ У вас нет подключенного VPN.")
        return

    key_id, expire_at = row
    expire_time = datetime.datetime.fromisoformat(str(expire_at))

    if expire_time <= datetime.datetime.now():
        await callback.message.answer("❌ Ваш VPN истёк.")
        return

    # Проверка лимита устройств
    if not await can_add_device(user_id):
        await callback.message.answer("❌ Достигнут лимит устройств (3).")
        return

    # Добавляем устройство
    await add_device(user_id, f"device_{int(time.time())}")

    # Получаем текст ключа из Outline API
    outline_key_text = get_outline_key(key_id)  # синхронная функция

    # Отправляем пользователю
    await bot.send_message(
        user_id,
        f"📦 Ваш VPN:\n`{outline_key_text}`",
        parse_mode="Markdown"
    )

# ================== START ==================

@dp.message(CommandStart())
async def start(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("👑 Админ-панель", reply_markup=admin_menu())
    else:
        await message.answer("🚀 Добро пожаловать!", reply_markup=main_menu())

# ================== TRIAL ======================
@dp.callback_query(lambda c: c.data == "trial")
async def trial(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    # Проверяем, использовал ли пользователь trial
    if await is_trial_used(user_id):
        await callback.message.answer("❌ Пробная подписка уже была активирована.")
        return

    # Проверяем лимит устройств
    if not await can_add_device(user_id):
        await callback.message.answer("❌ Достигнут лимит устройств (3).")
        return

    # Генерируем ключ Outline (функция синхронная, без await)
    try:
        outline_key_text, key_id = create_outline_key()  # исправлено
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации ключа: {e}")
        return

    # Срок триала
    expire = datetime.datetime.now() + datetime.timedelta(days=3)

    # Сохраняем пользователя в базе
    await activate_user(user_id, key_id, expire)
    await set_trial_used(user_id)
    await add_device(user_id, f"trial_device_{int(time.time())}")

    # Отправляем ключ пользователю
    await bot.send_message(
        user_id,
        f"🎁 Пробная подписка активирована!\n\nВаш VPN:\n`{outline_key_text}`",
        parse_mode="Markdown"
    )
# ================== HOW TO CONNECT ==================

@dp.callback_query(lambda c: c.data == "how_to_connect")
async def how_to_connect(callback: types.CallbackQuery):

    text = """
📲 <b>Как подключить VPN через V2RayTun</b>

📱 <b>Android</b>:
1. Установите приложение <b>V2RayTun</b> из Google Play.
2. Нажмите ➕, чтобы добавить новый профиль.
3. Выберите «Импорт из ссылки» или «Import from URL».
4. Вставьте полученный ключ/ссылку вашего VPN.
5. Сохраните профиль и активируйте подключение.

🍎 <b>iPhone</b>:
1. Установите приложение <b>V2RayTun</b> из App Store.
2. Нажмите «Добавить профиль» / «Add Profile».
3. Выберите «Import from URL» и вставьте ссылку ключа.
4. Сохраните профиль и включите подключение.

💻 <b>Windows / Mac</b>:
1. Установите <b>V2RayTun</b> с официального сайта.
2. Откройте приложение и нажмите «Добавить» / «Add Profile».
3. Выберите «Import from URL» и вставьте ссылку ключа.
4. Сохраните профиль и подключитесь к VPN.
"""

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# ================== BACK ==================

@dp.callback_query(lambda c: c.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()

# ================== SUPPORT ==================

@dp.callback_query(lambda c: c.data == "support")
async def support(callback: types.CallbackQuery):
    support_menu = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="@bekcka", url="https://t.me/bekcka"),
            InlineKeyboardButton(text="@woo0qp", url="https://t.me/woo0qp")
        ],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
    await callback.message.edit_text("🛟 Выберите кому написать:", reply_markup=support_menu)
    await callback.answer()

# ================== ТАРИФЫ ==================

@dp.callback_query(lambda c: c.data == "tariffs")
async def show_tariffs(callback: types.CallbackQuery):
    await callback.message.edit_text("💳 Выберите тариф:", reply_markup=tariffs_menu())
    await callback.answer()

# ================== ОПЛАТА ЧЕРЕЗ КАРТУ ==================

@dp.callback_query(lambda c: c.data.startswith("tariff_"))
async def tariff_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    months = int(callback.data.split("_")[1])

    price_map = {1: 100, 3: 200, 6: 400, 12: 800}
    price = price_map[months]

    pending_payments[user_id] = {"months": months, "price": price}

    await callback.message.edit_text(
        f"💳 Переведите {price}р на карту.\nYoomoney:2200153644651862\n"
        f"После оплаты отправьте последние 4 цифры номера вашей карты,мы проверим что вы все оплатили."
    )
    await callback.answer()

# ================== ЗАЯВКА АДМИНУ ==================

@dp.message()
async def payment_request(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pending_payments:
        return

    # Сохраняем последние 4 цифры
    digits = message.text[-4:]  # берём последние 4 символа
    pending_payments[user_id]['digits'] = digits

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}")
    ]])

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"💰 Новая заявка\nПользователь: {user_id}\n"
            f"Тариф: {pending_payments[user_id]['months']} мес\n"
            f"Цена: {pending_payments[user_id]['price']}р\n"
            f"Последние 4 цифры карты: {digits}",
            reply_markup=keyboard
        )

    await message.answer("⏳ Заявка отправлена администратору.")

# ================== ПОДТВЕРЖДЕНИЕ ==================

@dp.callback_query(lambda c: c.data.startswith("confirm_"))
async def confirm(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    user_id = int(callback.data.split("_")[1])

    if user_id not in pending_payments:
        await callback.answer("Нет заявки")
        return

    data = pending_payments.pop(user_id)
    months = data["months"]

    days_map = {1: 30, 3: 90, 6: 180, 12: 365}
    expire = datetime.datetime.now() + datetime.timedelta(days=days_map[months])

    # 🔥 создаём ключ Outline
    vpn_key, key_id = create_outline_key()

    if not vpn_key:
        await bot.send_message(user_id, "❌ Ошибка создания VPN ключа.")
        return

    # сохраняем В БАЗУ key_id (ВАЖНО!)
    await activate_user(user_id, key_id, expire)

    # отправляем пользователю ss:// ключ
    await bot.send_message(
        user_id,
        f"✅ Оплата подтверждена!\n\nВаш VPN:\n`{vpn_key}`",
        parse_mode="Markdown"
    )

    await callback.message.edit_text("✅ Подтверждено.")
    await callback.answer()
# ================== FUNCTION ==============

def get_outline_key(key_id):
    url = f"{OUTLINE_API_URL}/access-keys/{key_id}"

    response = requests.get(url, verify=False)

    if response.status_code == 200:
        return response.json()["accessUrl"]

    return None

async def can_add_device(user_id):
    count = await device_count(user_id)
    return count < MAX_DEVICES

def delete_outline_key(key_id):
    requests.delete(f"{OUTLINE_API_URL}/access-keys/{key_id}")

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Активные пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

@dp.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, expire_at
            FROM users
            WHERE expire_at > ?
        """, (datetime.datetime.now(),))
        users = await cursor.fetchall()


    if not users:
        await callback.message.answer("📭 Нет активных пользователей.")
        return

    text = "📊 <b>Активные пользователи:</b>\n\n"

    for user_id, expire_at in users:
        expire_time = datetime.datetime.fromisoformat(str(expire_at))

        # определяем тариф по сроку
        days_left = (expire_time - datetime.datetime.now()).days

        if days_left <= 3:
            tariff = "🎁 Trial"
        else:
            tariff = "💳 Платный"

        text += f"👤 ID: {user_id}\n📦 Тариф: {tariff}\n⏳ До: {expire_time.strftime('%d.%m.%Y')}\n\n"

    await callback.message.answer(text, parse_mode="HTML")

async def check_expired():
    while True:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT user_id, outline_key_id
                FROM users
                WHERE expire_at <= ?
            """, (datetime.datetime.now(),))

            expired_users = await cursor.fetchall()

            for user_id, key_id in expired_users:
                # Удаляем ключ из Outline
                if key_id:
                    try:
                        await delete_outline_key(key_id)  # твоя функция для Outline API
                    except Exception as e:
                        print(f"Ошибка при удалении ключа {key_id}: {e}")

                # Удаляем пользователя из базы
                await db.execute("DELETE FROM users WHERE user_id=?", (user_id,))

                # Сообщаем пользователю
                try:
                    await bot.send_message(user_id, "❌ Ваша подписка закончилась.")
                except:
                    pass

            await db.commit()
        await asyncio.sleep(3600)  # проверка каждый час


def create_outline_key():
    url = f"{OUTLINE_API_URL}/access-keys"

    response = requests.post(url, verify=False)  # 🔥 ВАЖНО

    if response.status_code == 201:
        data = response.json()
        return data["accessUrl"], data["id"]
    else:
        print("Ошибка создания ключа:", response.text)
        return None, None


@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_payment(callback: types.CallbackQuery):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа")
        return

    user_id = int(callback.data.split("_")[1])

    if user_id in pending_payments:
        pending_payments.pop(user_id)

    await bot.send_message(user_id, "❌ Ваша заявка на оплату отклонена.")

    await callback.message.edit_text("❌ Заявка отклонена.")
    await callback.answer("Отклонено")

def get_free_config(user_id):
    files = os.listdir(CONFIGS_DIR)

    for file in files:
        if file not in used_configs.values():
            used_configs[user_id] = file
            return os.path.join(CONFIGS_DIR, file)

    return None
# ================== MAIN ==================

async def main():
    await init_db()

    asyncio.create_task(check_expired())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
