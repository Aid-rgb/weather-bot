import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Загружаем .env при локальном запуске (на Railway переменная задаётся в настройках)
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден! Установи переменную окружения или создай .env файл")

# Города: название кнопки -> поисковый запрос для геокодера
# None означает что координаты заданы вручную в MANUAL_COORDS
goroda = {
    "Симферополь":  "Симферополь",
    "Севастополь":  "Севастополь",
    "Феодосия":     "Феодосия",
    "Ялта":         "Ялта",
    "Алушта":       "Алушта",
    "Джанкой":      "Джанкой",
    "Кировское":    "Kirovske",
}

# Ручные координаты для населённых пунктов которых нет в геокодере
MANUAL_COORDS = {}

# Порядок кнопок
goroda_list = [
    "Симферополь", "Севастополь",
    "Феодосия",    "Ялта",
    "Алушта",      "Джанкой",
    "Кировское",
]


def city_keyboard():
    """Клавиатура выбора города."""
    rows = []
    row = []
    for city in goroda_list:
        row.append(InlineKeyboardButton(city, callback_data=f"city:{city}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def day_keyboard(city: str):
    """Клавиатура выбора дня, передаём выбранный город в callback_data."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data=f"day:today:{city}"),
            InlineKeyboardButton("📆 Завтра",  callback_data=f"day:tomorrow:{city}"),
        ]
    ])


def load_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def get_coord(city: str):
    """Возвращает координаты города. Сначала проверяет ручные координаты."""
    if city in MANUAL_COORDS:
        return MANUAL_COORDS[city]

    query = goroda[city]
    params = urllib.parse.urlencode({
        "name": query,
        "count": 1,
        "language": "ru",
        "format": "json",
    })
    data = load_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    result = data.get("results")
    if not result:
        return None
    c = result[0]
    return {"name": c.get("name", query), "lat": c["latitude"], "lon": c["longitude"]}


def get_weather(lat, lon):
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,weather_code",
        "timezone": "auto",
        "forecast_days": 2,
    })
    return load_json(f"https://api.open-meteo.com/v1/forecast?{params}")


def weather_code_to_text(code):
    weather_map = {
        0:  "Ясно ☀️",
        1:  "Преимущественно ясно 🌤",
        2:  "Переменная облачность ⛅️",
        3:  "Пасмурно ☁️",
        45: "Туман 🌫",
        48: "Туман с инеем 🌫",
        51: "Слабая морось 🌦",
        53: "Умеренная морось 🌦",
        55: "Сильная морось 🌧",
        56: "Слабая ледяная морось 🌧",
        57: "Сильная ледяная морось 🌧",
        61: "Слабый дождь 🌧",
        63: "Умеренный дождь 🌧",
        65: "Сильный дождь 🌧",
        66: "Слабый ледяной дождь 🌧",
        67: "Сильный ледяной дождь 🌧",
        71: "Слабый снег ❄️",
        73: "Умеренный снег ❄️",
        75: "Сильный снег ❄️",
        77: "Снежные зерна ❄️",
        80: "Слабые ливни 🌧",
        81: "Умеренные ливни 🌧",
        82: "Сильные ливни 🌧",
        85: "Слабый снегопад ❄️",
        86: "Сильный снегопад ❄️",
        95: "Гроза ⛈",
        96: "Гроза со слабым градом ⛈",
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

    # Текущая погода только для «сегодня»
    if day == "today":
        lines.append("━━━ Сейчас ━━━")
        lines.append(weather_code_to_text(now["weather_code"]))
        lines.append(f"🌡 Температура: {now['temperature_2m']}°C")
        lines.append(f"🤔 Ощущается как: {now['apparent_temperature']}°C")
        lines.append(f"💨 Ветер: {now['wind_speed_10m']} км/ч")
        lines.append("")

    lines.append(f"━━━ Прогноз на {day_label} ━━━")
    lines.append("")

    # Каждые 2 часа
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
        lines.append("")  # пустая строка между записями

    return "\n".join(lines)


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — показываем выбор города."""
    await update.message.reply_text(
        "Привет! Выбери населённый пункт:",
        reply_markup=city_keyboard()
    )


async def on_city_chosen(query, city: str):
    """Пользователь выбрал город — редактируем сообщение, показываем выбор дня."""
    await query.edit_message_text(
        f"📍 {city}\n\nНа какой день показать погоду?",
        reply_markup=day_keyboard(city)
    )


async def on_day_chosen(query, day: str, city: str):
    """Пользователь выбрал день — удаляем меню, отправляем прогноз, затем новое меню."""
    await query.edit_message_text(f"⏳ Получаю погоду для «{city}»...")

    try:
        city_info = get_coord(city)
        if city_info is None:
            await query.edit_message_text(
                "Не удалось найти координаты. Попробуй позже.",
                reply_markup=city_keyboard()
            )
            return

        pogoda = get_weather(city_info["lat"], city_info["lon"])
        text   = make_text(city_info["name"], pogoda, day)

        # Удаляем сообщение "⏳ Получаю погоду..."
        await query.delete_message()

        # Прогноз остаётся навсегда
        await query.message.chat.send_message(text)

        # Новое меню выбора города
        await query.message.chat.send_message(
            "Выбери населённый пункт:",
            reply_markup=city_keyboard()
        )

    except Exception as e:
        await query.edit_message_text(
            f"Ошибка: {e}\nПопробуй позже.",
            reply_markup=city_keyboard()
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый обработчик всех inline-кнопок."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("city:"):
        city = data.split(":", 1)[1]
        await on_city_chosen(query, city)
    elif data.startswith("day:"):
        _, day, city = data.split(":", 2)
        await on_day_chosen(query, day, city)


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
