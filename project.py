import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = "8786452529:AAHZcL2gc1E1jHQ2mUdHuirHoafKi9ZcOkQ"

# список городов (кнопка -> поисковый запрос для геокодера)
goroda = {
    "Симферополь": "Симферополь",
    "Севастополь": "Севастополь",
    "Феодосия": "Феодосия",
    "Ялта": "Ялта",
    "Джанкой": "Джанкой",
    "Кировское": "Kirovske",
}

# порядок городов для отображения кнопок
goroda_list = ["Симферополь", "Севастополь", "Феодосия", "Ялта", "Джанкой", "Кировское"]


def day_keyboard():
    """Клавиатура выбора дня."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="day:today"),
            InlineKeyboardButton("📆 Завтра",  callback_data="day:tomorrow"),
        ]
    ])


def city_keyboard(day: str):
    """Клавиатура выбора города, передаём выбранный день в callback_data."""
    rows = []
    row = []
    for i, city in enumerate(goroda_list):
        row.append(InlineKeyboardButton(city, callback_data=f"city:{day}:{city}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def load_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def get_coord(city_query):
    params = urllib.parse.urlencode({
        "name": city_query,
        "count": 1,
        "language": "ru",
        "format": "json",
    })
    data = load_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    result = data.get("results")
    if not result:
        return None
    c = result[0]
    return {"name": c.get("name", city_query), "lat": c["latitude"], "lon": c["longitude"]}


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
        0: "Ясно ☀️", 1: "Преимущественно ясно 🌤", 2: "Переменная облачность ⛅️",
        3: "Пасмурно ☁️", 45: "Туман 🌫", 48: "Туман с инеем 🌫",
        51: "Слабая морось 🌦", 53: "Умеренная морось 🌦", 55: "Сильная морось 🌧",
        56: "Слабая ледяная морось 🌧", 57: "Сильная ледяная морось 🌧",
        61: "Слабый дождь 🌧", 63: "Умеренный дождь 🌧", 65: "Сильный дождь 🌧",
        66: "Слабый ледяной дождь 🌧", 67: "Сильный ледяной дождь 🌧",
        71: "Слабый снег ❄️", 73: "Умеренный снег ❄️", 75: "Сильный снег ❄️",
        77: "Снежные зерна ❄️", 80: "Слабые ливни 🌧", 81: "Умеренные ливни 🌧",
        82: "Сильные ливни 🌧", 85: "Слабый снегопад ❄️", 86: "Сильный снегопад ❄️",
        95: "Гроза ⛈", 96: "Гроза со слабым градом ⛈", 99: "Гроза с сильным градом ⛈",
    }
    return weather_map.get(code, "Неизвестно 🌈")


def make_text(city_name, pogoda, day: str):
    now = pogoda["current"]
    hours = pogoda["hourly"]
    now_time = datetime.fromisoformat(now["time"])
    today = now_time.date()
    tomorrow = today + timedelta(days=1)

    target_date = today if day == "today" else tomorrow
    day_label = "сегодня" if day == "today" else f"завтра ({tomorrow.strftime('%d.%m')})"

    parts = [f"🏙 Погода: {city_name} — {day_label}\n"]

    # Текущая погода только для «сегодня»
    if day == "today":
        parts.append("━━━ Сейчас ━━━")
        parts.append(weather_code_to_text(now["weather_code"]))
        parts.append(f"🌡 Температура: {now['temperature_2m']}°C")
        parts.append(f"🤔 Ощущается как: {now['apparent_temperature']}°C")
        parts.append(f"💨 Ветер: {now['wind_speed_10m']} км/ч\n")

    # Почасовой прогноз
    rows = []
    for i in range(len(hours["time"])):
        hour_time = datetime.fromisoformat(hours["time"][i])
        if hour_time.date() != target_date:
            continue
        if day == "today" and hour_time.hour < now_time.hour:
            continue
        rows.append(
            f"  {hour_time.strftime('%H:%M')} — {weather_code_to_text(hours['weather_code'][i])}\n"
            f"  🌡 {hours['temperature_2m'][i]}°C  "
            f"🌧 {hours['precipitation_probability'][i]}%  "
            f"💨 {hours['wind_speed_10m'][i]} км/ч"
        )

    if rows:
        parts.append(f"━━━ Прогноз на {day_label} ━━━")
        parts.extend(rows)

    return "\n".join(parts)


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — показываем выбор дня."""
    await update.message.reply_text(
        "Привет! На какой день показать погоду?",
        reply_markup=day_keyboard()
    )


async def on_day_chosen(query, day: str):
    """Пользователь выбрал день — редактируем сообщение, показываем города."""
    day_label = "сегодня" if day == "today" else "завтра"
    await query.edit_message_text(
        f"Выбран день: {'📅 Сегодня' if day == 'today' else '📆 Завтра'}\n\nТеперь выбери населённый пункт:",
        reply_markup=city_keyboard(day)
    )


async def on_city_chosen(query, day: str, city: str):
    """Пользователь выбрал город — редактируем сообщение, показываем погоду."""
    await query.edit_message_text(f"⏳ Получаю погоду для «{city}»...")

    try:
        city_info = get_coord(goroda[city])
        if city_info is None:
            await query.edit_message_text(
                "Не удалось найти координаты города. Попробуй позже.",
                reply_markup=day_keyboard()
            )
            return

        pogoda = get_weather(city_info["lat"], city_info["lon"])
        text = make_text(city_info["name"], pogoda, day)

        # Кнопка «Назад» — вернуться к выбору города
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Выбрать другой город", callback_data=f"day:{day}")],
            [InlineKeyboardButton("🏠 В начало", callback_data="home")],
        ])
        await query.edit_message_text(text, reply_markup=back_kb)

    except Exception as e:
        await query.edit_message_text(
            f"Ошибка: {e}\nПопробуй позже.",
            reply_markup=day_keyboard()
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый обработчик всех inline-кнопок."""
    query = update.callback_query
    await query.answer()  # убираем «часики» на кнопке

    data = query.data

    if data == "home":
        await query.edit_message_text(
            "На какой день показать погоду?",
            reply_markup=day_keyboard()
        )
    elif data.startswith("day:"):
        day = data.split(":")[1]
        await on_day_chosen(query, day)
    elif data.startswith("city:"):
        _, day, city = data.split(":", 2)
        await on_city_chosen(query, day, city)


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
