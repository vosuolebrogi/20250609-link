import os
import re
import logging
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, unquote
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получение токена из переменной окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class LinkBuilder(StatesGroup):
    waiting_for_campaign = State()
    waiting_for_action_type = State()
    waiting_for_service = State()
    waiting_for_route_start = State()
    waiting_for_route_end = State()
    waiting_for_custom_deeplink = State()
    waiting_for_desktop_url = State()


def transliterate_to_latin(text: str) -> str:
    """Транслитерация кириллицы в латиницу и удаление спецсимволов"""
    cyrillic_to_latin = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    result = ""
    for char in text.lower():
        if char in cyrillic_to_latin:
            result += cyrillic_to_latin[char]
        elif char.isalnum():
            result += char
        # Спецсимволы игнорируем
    
    return result


def is_valid_url(url: str) -> bool:
    """Проверка валидности URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def build_final_link(user_data: Dict[str, Any]) -> str:
    """Построение финальной ссылки"""
    # Базовая часть ссылки
    base_url = "https://yandex.go.link/"
    
    # Получаем диплинк
    deeplink = user_data.get('deeplink', '')
    if deeplink.startswith('yandextaxi://'):
        deeplink = deeplink[13:]  # Убираем yandextaxi://
    
    # Параметры
    today = datetime.now().strftime('%Y%m%d')
    params = {
        'adj_t': '1md8ai4n_1mztz3nz',
        'adj_campaign': f'{today}_bot',
        'adj_adgroup': transliterate_to_latin(user_data.get('campaign_name', ''))
    }
    
    # Добавляем fallback если есть
    if user_data.get('desktop_url'):
        params['adj_fallback'] = quote(user_data['desktop_url'])
    
    # Строим URL
    param_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    
    # Определяем разделитель - ? если в deeplink нет параметров, & если есть
    separator = '&' if '?' in deeplink else '?'
    final_url = f"{base_url}{deeplink}{separator}{param_string}"
    
    return final_url


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    await message.answer(
        "🚗 Привет! Я помогу тебе создать ссылку на приложение Яндекс Go.\n\n"
        "Для начала, опиши одним словом название кампании для которой делается ссылка:"
    )
    await LinkBuilder.waiting_for_campaign.set()


@dp.message_handler(state=LinkBuilder.waiting_for_campaign)
async def process_campaign(message: types.Message, state: FSMContext):
    """Обработка названия кампании"""
    campaign_name = message.text.strip()
    
    if not campaign_name or len(campaign_name.split()) > 1:
        await message.answer("❌ Пожалуйста, введи название кампании одним словом:")
        return
    
    await state.update_data(campaign_name=campaign_name)
    
    # Создаем клавиатуру для выбора действия
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("Просто открыть приложение"))
    keyboard.add(KeyboardButton("Диплинк сервиса"))
    keyboard.add(KeyboardButton("Диплинк маршрута"))
    keyboard.add(KeyboardButton("Свой диплинк"))
    
    await message.answer(
        "✅ Отлично! Теперь выбери, что должно происходить при клике на ссылку:",
        reply_markup=keyboard
    )
    await LinkBuilder.waiting_for_action_type.set()


@dp.message_handler(state=LinkBuilder.waiting_for_action_type)
async def process_action_type(message: types.Message, state: FSMContext):
    """Обработка типа действия"""
    action = message.text.strip()
    
    if action == "Просто открыть приложение":
        await state.update_data(deeplink="yandextaxi://")
        await ask_desktop_url(message, state)
        
    elif action == "Диплинк сервиса":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(KeyboardButton("Еда"))
        keyboard.add(KeyboardButton("Лавка"))
        keyboard.add(KeyboardButton("Драйв"))
        
        await message.answer(
            "Выбери сервис:",
            reply_markup=keyboard
        )
        await LinkBuilder.waiting_for_service.set()
        
    elif action == "Диплинк маршрута":
        await message.answer(
            "🚩 Введи адрес отправления (или нажми 'Пропустить', если не нужен):",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(KeyboardButton("Пропустить"))
        )
        await LinkBuilder.waiting_for_route_start.set()
        
    elif action == "Свой диплинк":
        await message.answer(
            "🔗 Введи свой диплинк в формате yandextaxi://mydeeplink:",
            reply_markup=ReplyKeyboardRemove()
        )
        await LinkBuilder.waiting_for_custom_deeplink.set()
        
    else:
        await message.answer("❌ Пожалуйста, выбери один из предложенных вариантов.")


@dp.message_handler(state=LinkBuilder.waiting_for_service)
async def process_service(message: types.Message, state: FSMContext):
    """Обработка выбора сервиса"""
    service_map = {
        "Еда": "eats",
        "Лавка": "grocery", 
        "Драйв": "drive"
    }
    
    service_name = message.text.strip()
    if service_name not in service_map:
        await message.answer("❌ Пожалуйста, выбери один из предложенных сервисов.")
        return
    
    service_code = service_map[service_name]
    deeplink = f"yandextaxi://external?service={service_code}"
    await state.update_data(deeplink=deeplink)
    
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_route_start)
async def process_route_start(message: types.Message, state: FSMContext):
    """Обработка адреса отправления"""
    start_address = message.text.strip()
    
    if start_address.lower() == "пропустить":
        start_address = ""
    
    await state.update_data(start_address=start_address)
    
    await message.answer(
        "🎯 Введи адрес назначения (или нажми 'Пропустить', если не нужен):",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(KeyboardButton("Пропустить"))
    )
    await LinkBuilder.waiting_for_route_end.set()


@dp.message_handler(state=LinkBuilder.waiting_for_route_end)
async def process_route_end(message: types.Message, state: FSMContext):
    """Обработка адреса назначения"""
    end_address = message.text.strip()
    
    if end_address.lower() == "пропустить":
        end_address = ""
    
    user_data = await state.get_data()
    start_address = user_data.get('start_address', '')
    
    # Формируем диплинк маршрута
    params = []
    if start_address:
        params.append(f"start={quote(start_address)}")
    if end_address:
        params.append(f"end={quote(end_address)}")
    
    if params:
        deeplink = f"yandextaxi://route?{'&'.join(params)}"
    else:
        deeplink = "yandextaxi://route"
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_custom_deeplink)
async def process_custom_deeplink(message: types.Message, state: FSMContext):
    """Обработка пользовательского диплинка"""
    deeplink = message.text.strip()
    
    if not deeplink.startswith("yandextaxi://"):
        await message.answer("❌ Диплинк должен начинаться с 'yandextaxi://'. Попробуй ещё раз:")
        return
    
    # Проверяем наличие параметра href и его URL-кодирование
    if "href=" in deeplink:
        try:
            # Извлекаем часть после yandextaxi://
            deeplink_part = deeplink[13:]  # убираем yandextaxi://
            
            # Если есть параметры
            if "?" in deeplink_part:
                query_part = deeplink_part.split("?", 1)[1]
                params = parse_qs(query_part)
                
                if "href" in params:
                    href_value = params["href"][0]
                    
                    # Проверяем, является ли значение href URL-кодированным
                    # Если после декодирования значение изменилось, значит оно было кодировано
                    decoded_href = unquote(href_value)
                    
                    # Проверяем наличие символов, которые должны быть закодированы
                    needs_encoding = any(char in href_value for char in ['%20', '%3A', '%2F', '%3F', '%26', '%3D'])
                    
                    if not needs_encoding and any(char in decoded_href for char in [' ', ':', '/', '?', '&', '=']):
                        await message.answer(
                            "❌ Параметр href должен быть URL-кодирован!\n"
                            f"Например: вместо '{decoded_href}' используй '{quote(decoded_href)}'\n\n"
                            "Попробуй ещё раз:"
                        )
                        return
                        
        except Exception as e:
            await message.answer("❌ Ошибка при проверке диплинка. Попробуй ещё раз:")
            return
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


async def ask_desktop_url(message: types.Message, state: FSMContext):
    """Запрос URL для десктопа"""
    await message.answer(
        "💻 Введи URL для открытия с десктопа (опционально).\n"
        "Или нажми 'Пропустить', если не нужен:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(KeyboardButton("Пропустить"))
    )
    await LinkBuilder.waiting_for_desktop_url.set()


@dp.message_handler(state=LinkBuilder.waiting_for_desktop_url)
async def process_desktop_url(message: types.Message, state: FSMContext):
    """Обработка URL для десктопа"""
    desktop_url = message.text.strip()
    
    if desktop_url.lower() != "пропустить":
        if not is_valid_url(desktop_url):
            await message.answer("❌ Введи корректный URL (должен начинаться с http:// или https://). Попробуй ещё раз:")
            return
        await state.update_data(desktop_url=desktop_url)
    
    # Генерируем финальную ссылку
    user_data = await state.get_data()
    final_link = build_final_link(user_data)
    
    # Создаём ссылку для сокращения
    encoded_link = quote(final_link)
    shortener_url = f"https://go-admin-frontend.taxi.yandex-team.ru/adjust?url={encoded_link}"
    
    await message.answer(
        f"🎉 Готово! Твоя ссылка:\n\n"
        f"`{final_link}`\n\n"
        f"📋 Скопируй ссылку выше и используй в своей кампании!\n\n"
        f"📱 Для использования в SMS или QR-кодах рекомендуется сократить ссылку:\n"
        f"[Перейти к сокращению ссылки]({shortener_url})\n\n"
        f"Чтобы создать новую ссылку, отправь /start",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    await state.finish()


@dp.message_handler()
async def handle_other_messages(message: types.Message):
    """Обработка прочих сообщений"""
    await message.answer(
        "🤖 Привет! Чтобы создать ссылку на Яндекс Go, отправь команду /start"
    )


if __name__ == '__main__':
    print("🚀 Запуск бота...")
    executor.start_polling(dp, skip_updates=True)