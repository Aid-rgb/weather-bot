import json
import os
import shelve
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, time

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден!")

DB_FILE = "favorites"  # shelve создаст favorites.db

# ─── Города ──────────────────────────────────────────────────────────────────

goroda = {
    "Симферополь": "Симферополь",
    "Севастополь": "Севастополь",
    "Балаклава":   "Балаклава",
    "Инкерман":    "Инкерман",
    "Феодосия":    "Феодосия",
    "Ялта":        "Ялта",
    "Алушта":      "Алушта",
    "Евпатория":   "Евпатория",
    "Керчь":       "Керчь",
    "Джанкой":     "Джанкой",
    "Кировское":   "Kirovske",
}

goroda_list = [
    "Симферополь", "Севастополь",
    "Балаклава",   "Инкерман",
    "Феодосия",    "Ялта",
    "Алушта",      "Евпатория",
    "Керчь",       "Джанкой",
    "Кировское",
]

# ─── Избранное (shelve) ───────────────────────────────────────────────────────

def get_favorite(user_id: int) -> str | None:
    with shelve.open(DB_FILE) as db:
        return db.get(str(user_id))

def set_favorite(user_id: int, city: str):
    with shelve.open(DB_FILE) as db:
        db[str(user_id)] = city

def remove_favorite(user_id: int):
    with shelve.open(DB_FILE) as db:
        db.pop(str(user_id), None)

def get_all_favorites() -> dict:
    """Возвращает {user_id: city} для всех пользователей с избранным."""
    with shelve.open(DB_FILE) as db:
        return dict(db)

# ─── Клавиатуры ──────────────────────────────────────────────────────────────

def city_keyboard(user_id: int):
    """Список городов + кнопка избранного внизу."""
    rows = []
    row = []
    for city in goroda_list:
        row.append(InlineKeyboardButton(city, callback_data=f"city:{city}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    fav = get_favorite(user_id)
    if fav:
        rows.append([InlineKeyboardButton(f"⭐️ {fav} (избранное)", callback_data=f"city:{fav}")])
        rows.append([InlineKeyboardButton("❌ Убрать из избранного", callback_data="fav:remove")])
    else:
        rows.append([InlineKeyboardButton("ℹ️ Нажми ⭐️ у города чтобы добавить в избранное", callback_data="noop")])

    return InlineKeyboardMarkup(rows)


def day_keyboard(city: str, user_id: int):
    """Выбор дня + кнопка добавить/убрать избранное."""
    fav = get_favorite(user_id)
    if fav == city:
        fav_btn = InlineKeyboardButton("❌ Убрать из избранного", callback_data=f"fav:remove")
    else:
        fav_btn = InlineKeyboardButton("⭐️ В избранное", callback_data=f"fav:add:{city}")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data=f"day:today:{city}"),
            InlineKeyboardButton("📆 Завтра",  callback_data=f"day:tomorrow:{city}"),
        ],
        [fav_btn],
        [InlineKeyboardButton("🔙 Назад", callback_data="back:cities")],
    ])

# ─── API ──────────────────────────────────────────────────────────────────────

def load_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def get_coord(city: str):
    query = goroda[city]
    params = urllib.parse.urlencode({
        "name": query, "count": 1, "language": "ru", "format": "json",
    })
    data = load_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    result = data.get("results")
    if not result:
        return None
    c = result[0]
    return {"name": c.get("name", query), "lat": c["latitude"], "lon": c["longitude"]}


def get_weather(lat, lon):
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,weather_code",
        "timezone": "auto",
        "forecast_days": 2,
    })
    return load_json(f"https://api.open-meteo.com/v1/forecast?{params}")


def weather_code_to_text(code):
    weather_map = {
        0:  "Ясно ☀️",           1:  "Преимущественно ясно 🌤",
        2:  "Переменная облачность ⛅️", 3:  "Пасмурно ☁️",
        45: "Туман 🌫",           48: "Туман с инеем 🌫",
        51: "Слабая морось 🌦",   53: "Умеренная морось 🌦",
        55: "Сильная морось 🌧",  56: "Слабая ледяная морось 🌧",
        57: "Сильная ледяная морось 🌧",
        61: "Слабый дождь 🌧",   63: "Умеренный дождь 🌧",
        65: "Сильный дождь 🌧",  66: "Слабый ледяной дождь 🌧",
        67: "Сильный ледяной дождь 🌧",
        71: "Слабый снег ❄️",    73: "Умеренный снег ❄️",
        75: "Сильный снег ❄️",   77: "Снежные зерна ❄️",
        80: "Слабые ливни 🌧",   81: "Умеренные ливни 🌧",
        82: "Сильные ливни 🌧",  85: "Слабый снегопад ❄️",
        86: "Сильный снегопад ❄️",
        95: "Гроза ⛈",           96: "Гроза со слабым градом ⛈",
        99: "Гроза с сильным градом ⛈",
    }
    return weather_map.get(code, "Неизвестно 🌈")


def make_text(city_name, pogoda, day: str):
    now   = pogoda["current"]
    hours = pogoda["hourly"]

    now_time = datetime.fromisoformat(now["time"])
    today    = now_time.date()
    tomorrow = today + timedelta(days=1)

    target_date = today if day == "today" else tomorrow
    day_label   = "сегодня" if day == "today" else f"завтра ({tomorrow.strftime('%d.%m')})"

    lines = []
    lines.append(f"🏙 Погода: {city_name} — {day_label}")
    lines.append("")

    if day == "today":
        lines.append("━━━ Сейчас ━━━")
        lines.append(weather_code_to_text(now["weather_code"]))
        lines.append(f"🌡 Температура: {now['temperature_2m']}°C")
        lines.append(f"🤔 Ощущается как: {now['apparent_temperature']}°C")
        lines.append(f"💨 Ветер: {now['wind_speed_10m']} км/ч")
        lines.append("")

    lines.append(f"━━━ Прогноз на {day_label} ━━━")
    lines.append("")

    for i in range(len(hours["time"])):
        hour_time = datetime.fromisoformat(hours["time"][i])
        if hour_time.date() != target_date:
            continue
        if day == "today" and hour_time.hour < now_time.hour:
            continue
        if hour_time.hour % 2 != 0:
            continue
        lines.append(f"🕐 {hour_time.strftime('%H:%M')} — {weather_code_to_text(hours['weather_code'][i])}")
        lines.append(f"   🌡 {hours['temperature_2m'][i]}°C   🌧 {hours['precipitation_probability'][i]}%   💨 {hours['wind_speed_10m'][i]} км/ч")
        lines.append("")

    return "\n".join(lines)

# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav = get_favorite(user_id)
    text = "Привет! Выбери населённый пункт:"
    if fav:
        text = f"Привет! Твоё избранное: ⭐️ {fav}\n\nВыбери населённый пункт:"
    await update.message.reply_text(text, reply_markup=city_keyboard(user_id))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data    = query.data
    user_id = query.from_user.id

    if data == "noop":
        return

    elif data == "back:cities":
        fav  = get_favorite(user_id)
        text = f"Твоё избранное: ⭐️ {fav}\n\nВыбери населённый пункт:" if fav else "Выбери населённый пункт:"
        await query.edit_message_text(text, reply_markup=city_keyboard(user_id))

    elif data.startswith("fav:add:"):
        city = data.split(":", 2)[2]
        set_favorite(user_id, city)
        await query.edit_message_text(
            f"⭐️ {city} добавлен в избранное!\n\nКаждый день в 00:00 буду присылать погоду на сегодня.\n\nНа какой день показать погоду?",
            reply_markup=day_keyboard(city, user_id)
        )

    elif data == "fav:remove":
        remove_favorite(user_id)
        await query.edit_message_text(
            "Избранное удалено.\n\nВыбери населённый пункт:",
            reply_markup=city_keyboard(user_id)
        )

    elif data.startswith("city:"):
        city = data.split(":", 1)[1]
        fav  = get_favorite(user_id)
        fav_note = f"\n⭐️ Это твоё избранное" if fav == city else ""
        await query.edit_message_text(
            f"📍 {city}{fav_note}\n\nНа какой день показать погоду?",
            reply_markup=day_keyboard(city, user_id)
        )

    elif data.startswith("day:"):
        _, day, city = data.split(":", 2)
        await query.edit_message_text(f"⏳ Получаю погоду для «{city}»...")
        try:
            city_info = get_coord(city)
            if city_info is None:
                await query.edit_message_text("Не удалось найти координаты. Попробуй позже.", reply_markup=city_keyboard(user_id))
                return
            pogoda = get_weather(city_info["lat"], city_info["lon"])
            text   = make_text(city_info["name"], pogoda, day)
            await query.delete_message()
            await query.message.chat.send_message(text)
            fav  = get_favorite(user_id)
            note = f"Твоё избранное: ⭐️ {fav}\n\n" if fav else ""
            await query.message.chat.send_message(
                f"{note}Выбери населённый пункт:",
                reply_markup=city_keyboard(user_id)
            )
        except Exception as e:
            await query.edit_message_text(f"Ошибка: {e}\nПопробуй позже.", reply_markup=city_keyboard(user_id))


# ─── Ежедневная рассылка в 00:00 ─────────────────────────────────────────────

async def daily_forecast(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет погоду на сегодня всем у кого есть избранное."""
    favorites = get_all_favorites()
    for user_id_str, city in favorites.items():
        try:
            city_info = get_coord(city)
            if city_info is None:
                continue
            pogoda = get_weather(city_info["lat"], city_info["lon"])
            text   = "⭐️ Доброе утро! Погода на сегодня для твоего избранного:\n\n"
            text  += make_text(city_info["name"], pogoda, "today")
            await context.bot.send_message(chat_id=int(user_id_str), text=text)
        except Exception:
            pass  # пользователь мог заблокировать бота — пропускаем


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Рассылка каждый день в 00:00 по московскому времени (UTC+3)
    app.job_queue.run_daily(
        daily_forecast,
        time=time(hour=0, minute=0, second=0),
        job_kwargs={"misfire_grace_time": 60},
    )

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
