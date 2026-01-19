import os
import re
import json
import logging
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, unquote
from typing import Dict, Any, Optional, Tuple, List

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

BACK_BUTTON_TEXT = "Назад"
GO_APP_NAME = "Go"

DEFAULT_APP_ORDER = [GO_APP_NAME]
DEFAULT_APP_CATALOG = {
    GO_APP_NAME: {
        "scheme": "yandextaxi://",
        "base_url": "https://yandex.go.link/"
    }
}


def normalize_base_url(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def load_app_catalog(paths: List[str]) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    data = None
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as file:
                raw = file.read().lstrip("\ufeff")
                data = json.loads(raw)
            break
        except FileNotFoundError:
            continue
        except Exception:
            data = None
            break

    if data is None:
        logging.warning("import.txt не найден или не распознан, использую дефолт.")
        return DEFAULT_APP_ORDER, DEFAULT_APP_CATALOG

    app_order: List[str] = []
    app_catalog: Dict[str, Dict[str, str]] = {}

    for table in data:
        if table.get("table_index") != 1:
            continue
        for row in table.get("table", []):
            app_name = row.get("App")
            scheme = row.get("Scheme")
            base_url = row.get("iOS Universal Deeplink")
            if not app_name or not scheme or not base_url:
                continue
            app_order.append(app_name)
            app_catalog[app_name] = {
                "scheme": scheme,
                "base_url": normalize_base_url(base_url)
            }
        break

    if not app_catalog:
        logging.warning("В import.txt нет таблицы с приложениями, использую дефолт.")
        return DEFAULT_APP_ORDER, DEFAULT_APP_CATALOG
    logging.info("Загружены приложения из import.txt: %s", ", ".join(app_order))
    return app_order, app_catalog


IMPORT_FILE_PATHS = [
    os.path.join(os.path.dirname(__file__), "import.txt"),
    os.path.join(os.getcwd(), "import.txt")
]
APP_ORDER, APP_CATALOG = load_app_catalog(IMPORT_FILE_PATHS)

APP_OPTIONS = APP_ORDER
REATTRIBUTION_OPTIONS = ["Да", "Только неактивных от 30 дней"]
TEMP_ATTR_OPTIONS = ["Без ограничений", "30 дней"]
ACTION_TYPE_OPTIONS = [
    "Просто открыть приложение",
    "Сервис",
    "Промокод",
    "Тариф",
    "Баннер",
    "Свой диплинк"
]
SERVICE_OPTIONS = ["Еда", "Лавка", "Драйв", "Маркет", "Самокаты"]
TARIFF_OPTIONS = [
    "Эконом",
    "Комфорт",
    "Комфорт+",
    "Бизнес",
    "Грузовой",
    "Детский",
    "Межгород",
    "Свой тариф"
]


class LinkBuilder(StatesGroup):
    waiting_for_app = State()
    waiting_for_reattribution = State()
    waiting_for_temporary_attribution = State()
    waiting_for_campaign = State()
    waiting_for_action_type = State()
    waiting_for_service = State()
    waiting_for_route_start = State()
    waiting_for_route_end = State()
    waiting_for_custom_deeplink = State()
    waiting_for_promo_code = State()
    waiting_for_tariff = State()
    waiting_for_custom_tariff = State()
    waiting_for_banner_id = State()
    waiting_for_desktop_url = State()


def make_keyboard(buttons=None, include_back=False) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for button_text in buttons or []:
        keyboard.add(KeyboardButton(button_text))
    if include_back:
        keyboard.add(KeyboardButton(BACK_BUTTON_TEXT))
    return keyboard


def keyboard_app() -> ReplyKeyboardMarkup:
    return make_keyboard(APP_OPTIONS, include_back=True)


def keyboard_reattribution() -> ReplyKeyboardMarkup:
    return make_keyboard(REATTRIBUTION_OPTIONS, include_back=True)


def keyboard_temp_attr() -> ReplyKeyboardMarkup:
    return make_keyboard(TEMP_ATTR_OPTIONS, include_back=True)


def keyboard_service() -> ReplyKeyboardMarkup:
    return make_keyboard(SERVICE_OPTIONS, include_back=True)


def keyboard_tariff() -> ReplyKeyboardMarkup:
    return make_keyboard(TARIFF_OPTIONS, include_back=True)


def keyboard_back_only() -> ReplyKeyboardMarkup:
    return make_keyboard(include_back=True)


def keyboard_skip_back() -> ReplyKeyboardMarkup:
    return make_keyboard(["Пропустить"], include_back=True)


def get_app_name_or_default(app_name: Optional[str]) -> str:
    if app_name in APP_CATALOG:
        return app_name
    return APP_ORDER[0] if APP_ORDER else GO_APP_NAME


def get_app_scheme(app_name: Optional[str]) -> str:
    app_name = get_app_name_or_default(app_name)
    return APP_CATALOG.get(app_name, DEFAULT_APP_CATALOG[GO_APP_NAME])["scheme"]


def get_app_base_url(app_name: Optional[str]) -> str:
    app_name = get_app_name_or_default(app_name)
    return APP_CATALOG.get(app_name, DEFAULT_APP_CATALOG[GO_APP_NAME])["base_url"]


def get_adj_t_map(app_name: Optional[str]) -> Dict[tuple, str]:
    app_name = get_app_name_or_default(app_name)
    if app_name == GO_APP_NAME:
        return {
            ('Да', 'Без ограничений'): '1pj8ktrc_1pksjytf',
            ('Только неактивных от 30 дней', 'Без ограничений'): '1md8ai4n_1mztz3nz',
            ('Да', '30 дней'): '1p5j0f1z_1pk9ju0y',
            ('Только неактивных от 30 дней', '30 дней'): '1pi2vjj3_1ppvctfa'
        }
    # Заглушки для трекеров остальных приложений — будут заменены позже
    return {
        ('Да', 'Без ограничений'): 'TODO_TRACKER_1',
        ('Только неактивных от 30 дней', 'Без ограничений'): 'TODO_TRACKER_2',
        ('Да', '30 дней'): 'TODO_TRACKER_3',
        ('Только неактивных от 30 дней', '30 дней'): 'TODO_TRACKER_4'
    }


def get_action_type_options(app_name: Optional[str]) -> List[str]:
    app_name = get_app_name_or_default(app_name)
    if app_name == GO_APP_NAME:
        return ACTION_TYPE_OPTIONS
    return ["Просто открыть приложение"]


def keyboard_action_type_for_app(app_name: Optional[str]) -> ReplyKeyboardMarkup:
    return make_keyboard(get_action_type_options(app_name), include_back=True)


def build_reattribution_text(app_name: Optional[str] = None) -> str:
    base_question = (
        "❓ Если у пользователя уже было приложение и он активен, нужно ли его "
        "атрибуцировать к этой ссылке?"
    )
    if app_name:
        return f"✅ Ок! Делаем ссылку для приложения {app_name}.\n\n{base_question}"
    return base_question


def build_temp_attr_text() -> str:
    return "⏰ Сколько пользователь должен оставаться в трекере после последнего контакта?"


async def prompt_app(message: types.Message) -> None:
    await message.answer(
        "📱 Привет! Для какого приложения нужно создать ссылку?",
        reply_markup=keyboard_app()
    )
    await LinkBuilder.waiting_for_app.set()


async def prompt_reattribution(
    message: types.Message,
    app_name: Optional[str] = None,
    error_prefix: Optional[str] = None
) -> None:
    text = build_reattribution_text(app_name)
    if error_prefix:
        text = f"{error_prefix}\n\n{text}"
    await message.answer(text, reply_markup=keyboard_reattribution())
    await LinkBuilder.waiting_for_reattribution.set()


async def prompt_temp_attr(
    message: types.Message,
    error_prefix: Optional[str] = None
) -> None:
    text = build_temp_attr_text()
    if error_prefix:
        text = f"{error_prefix}\n\n{text}"
    await message.answer(text, reply_markup=keyboard_temp_attr())
    await LinkBuilder.waiting_for_temporary_attribution.set()


async def prompt_campaign(message: types.Message) -> None:
    await message.answer(
        "📝 Теперь опиши одним словом название кампании для которой делается ссылка:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_campaign.set()


async def prompt_action_type_with_state(message: types.Message, state: FSMContext) -> None:
    user_data = await state.get_data()
    app_name = user_data.get("app", GO_APP_NAME)
    await message.answer(
        "✅ Отлично! Теперь выбери, что должно открываться при клике, если приложение уже есть на устройстве:",
        reply_markup=keyboard_action_type_for_app(app_name)
    )
    await LinkBuilder.waiting_for_action_type.set()


async def prompt_service(message: types.Message) -> None:
    await message.answer(
        "Выбери сервис:",
        reply_markup=keyboard_service()
    )
    await LinkBuilder.waiting_for_service.set()


async def prompt_tariff(message: types.Message) -> None:
    await message.answer(
        "🚗 Выбери тариф:",
        reply_markup=keyboard_tariff()
    )
    await LinkBuilder.waiting_for_tariff.set()


async def prompt_promo_code(message: types.Message) -> None:
    await message.answer(
        "🔗 Введи промокод:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_promo_code.set()


async def prompt_custom_tariff(message: types.Message) -> None:
    await message.answer(
        "📝 Введи код тарифа:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_custom_tariff.set()


async def prompt_banner_id(message: types.Message) -> None:
    await message.answer(
        "🎨 Введи ID баннера:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_banner_id.set()


async def prompt_custom_deeplink(message: types.Message, state: FSMContext) -> None:
    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))
    await message.answer(
        f"🔗 Введи свой диплинк в формате {scheme_prefix}mydeeplink:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_custom_deeplink.set()


async def prompt_route_start(message: types.Message) -> None:
    await message.answer(
        "🚩 Введи адрес отправления (или нажми 'Пропустить', если не нужен):",
        reply_markup=keyboard_skip_back()
    )
    await LinkBuilder.waiting_for_route_start.set()


async def prompt_route_end(message: types.Message) -> None:
    await message.answer(
        "🎯 Введи адрес назначения (или нажми 'Пропустить', если не нужен):",
        reply_markup=keyboard_skip_back()
    )
    await LinkBuilder.waiting_for_route_end.set()


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
    app_name = user_data.get('app', GO_APP_NAME)
    base_url = get_app_base_url(app_name)
    scheme_prefix = get_app_scheme(app_name)
    
    # Получаем диплинк
    deeplink = user_data.get('deeplink', '')
    if deeplink.startswith(scheme_prefix):
        deeplink = deeplink[len(scheme_prefix):]
    
    # Параметры
    today = datetime.now().strftime('%Y%m%d')
    campaign_value = f'{today}_bot'
    adgroup_value = transliterate_to_latin(user_data.get('campaign_name', ''))
    
    # Определяем adj_t на основе выбранных опций
    reattribution = user_data.get('reattribution', 'Только неактивных от 30 дней')
    temporary_attribution = user_data.get('temporary_attribution', 'Без ограничений')
    
    adj_t_map = get_adj_t_map(app_name)
    adj_t = adj_t_map.get(
        (reattribution, temporary_attribution),
        next(iter(adj_t_map.values()))
    )
    
    params = {
        'adj_t': adj_t,
        'adj_campaign': campaign_value,
        'adj_adgroup': adgroup_value
    }
    
    # Обрабатываем desktop_url если есть
    if user_data.get('desktop_url'):
        desktop_url = user_data['desktop_url']
        
        # Разбираем URL
        parsed_url = urlparse(desktop_url)
        query_params = parse_qs(parsed_url.query, keep_blank_values=True)
        
        # Добавляем utm_source если отсутствует
        if 'utm_source' not in query_params:
            query_params['utm_source'] = [campaign_value]
        
        # Добавляем utm_campaign если отсутствует  
        if 'utm_campaign' not in query_params:
            query_params['utm_campaign'] = [adgroup_value]
        
        # Пересобираем query string
        query_parts = []
        for key, values in query_params.items():
            for value in values:
                if value:
                    query_parts.append(f"{key}={quote(str(value))}")
                else:
                    query_parts.append(key)
        
        # Пересобираем URL
        if query_parts:
            new_query = '&'.join(query_parts)
            desktop_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?{new_query}"
            if parsed_url.fragment:
                desktop_url += f"#{parsed_url.fragment}"
        
        # Добавляем fallback и redirect_macos параметры
        params['adj_fallback'] = quote(desktop_url)
        params['adj_redirect_macos'] = quote(desktop_url)
    
    # Строим URL
    param_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    
    # Определяем разделитель - ? если в deeplink нет параметров, & если есть
    separator = '&' if '?' in deeplink else '?'
    final_url = f"{base_url}{deeplink}{separator}{param_string}"
    
    return final_url


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    await prompt_app(message)


@dp.message_handler(state=LinkBuilder.waiting_for_app)
async def process_app(message: types.Message, state: FSMContext):
    """Обработка выбора приложения"""
    app_name = message.text.strip()
    
    if app_name == BACK_BUTTON_TEXT:
        await prompt_app(message)
        return

    if app_name not in APP_OPTIONS:
        await message.answer(
            "❌ Пожалуйста, выбери одно из приложений кнопкой ниже:",
            reply_markup=keyboard_app()
        )
        return
    
    await state.update_data(app=app_name)
    
    await prompt_reattribution(message, app_name=app_name)


@dp.message_handler(state=LinkBuilder.waiting_for_reattribution)
async def process_reattribution(message: types.Message, state: FSMContext):
    """Обработка выбора реатрибуции"""
    reattribution = message.text.strip()
    
    if reattribution == BACK_BUTTON_TEXT:
        await prompt_app(message)
        return

    if reattribution not in REATTRIBUTION_OPTIONS:
        await prompt_reattribution(
            message,
            error_prefix="❌ Пожалуйста, используй кнопки для ответа."
        )
        return
    
    await state.update_data(reattribution=reattribution)
    
    await prompt_temp_attr(message)


@dp.message_handler(state=LinkBuilder.waiting_for_temporary_attribution)
async def process_temporary_attribution(message: types.Message, state: FSMContext):
    """Обработка выбора временной атрибуции"""
    temporary_attribution = message.text.strip()
    
    if temporary_attribution == BACK_BUTTON_TEXT:
        await prompt_reattribution(message)
        return

    if temporary_attribution not in TEMP_ATTR_OPTIONS:
        await prompt_temp_attr(
            message,
            error_prefix="❌ Пожалуйста, используй кнопки для ответа."
        )
        return
    
    await state.update_data(temporary_attribution=temporary_attribution)
    
    await prompt_campaign(message)


@dp.message_handler(state=LinkBuilder.waiting_for_campaign)
async def process_campaign(message: types.Message, state: FSMContext):
    """Обработка названия кампании"""
    campaign_name = message.text.strip()
    
    if campaign_name == BACK_BUTTON_TEXT:
        await prompt_temp_attr(message)
        return

    if not campaign_name or len(campaign_name.split()) > 1:
        await message.answer("❌ Пожалуйста, введи название кампании одним словом:")
        return
    
    await state.update_data(campaign_name=campaign_name)
    
    await prompt_action_type_with_state(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_action_type)
async def process_action_type(message: types.Message, state: FSMContext):
    """Обработка типа действия"""
    action = message.text.strip()
    
    if action == BACK_BUTTON_TEXT:
        await prompt_campaign(message)
        return

    user_data = await state.get_data()
    app_name = user_data.get("app", GO_APP_NAME)
    allowed_actions = get_action_type_options(app_name)

    if action not in allowed_actions:
        await message.answer(
            "❌ Пожалуйста, выбери один из предложенных вариантов.",
            reply_markup=keyboard_action_type_for_app(app_name)
        )
        return

    await state.update_data(action_type=action)

    if action == "Просто открыть приложение":
        await state.update_data(deeplink=get_app_scheme(app_name))
        await ask_desktop_url(message, state)
        
    elif action == "Сервис":
        await prompt_service(message)
        
    elif action == "Промокод":
        await prompt_promo_code(message)
        
    elif action == "Тариф":
        await prompt_tariff(message)
        
    elif action == "Баннер":
        await prompt_banner_id(message)
        
    elif action == "Свой диплинк":
        await prompt_custom_deeplink(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_service)
async def process_service(message: types.Message, state: FSMContext):
    """Обработка выбора сервиса"""
    # Специальные диплинки для некоторых сервисов
    special_service_map = {
        "Самокаты": "yandextaxi://scooters"
    }
    
    # Стандартные сервисы через external
    standard_service_map = {
        "Еда": "eats",
        "Лавка": "grocery", 
        "Драйв": "drive",
        "Маркет": "market"
    }
    
    service_name = message.text.strip()
    
    if service_name == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    # Проверяем специальные диплинки
    if service_name in special_service_map:
        deeplink = special_service_map[service_name]
    # Проверяем стандартные сервисы
    elif service_name in standard_service_map:
        service_code = standard_service_map[service_name]
        deeplink = f"yandextaxi://external?service={service_code}"
    else:
        await message.answer("❌ Пожалуйста, выбери один из предложенных сервисов.")
        return
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_route_start)
async def process_route_start(message: types.Message, state: FSMContext):
    """Обработка адреса отправления"""
    start_address = message.text.strip()
    
    if start_address == BACK_BUTTON_TEXT:
        await prompt_tariff(message)
        return

    if start_address.lower() == "пропустить":
        start_address = ""
    
    await state.update_data(start_address=start_address)
    
    await prompt_route_end(message)


@dp.message_handler(state=LinkBuilder.waiting_for_route_end)
async def process_route_end(message: types.Message, state: FSMContext):
    """Обработка адреса назначения"""
    end_address = message.text.strip()
    
    if end_address == BACK_BUTTON_TEXT:
        await prompt_route_start(message)
        return

    if end_address.lower() == "пропустить":
        end_address = ""
    
    user_data = await state.get_data()
    start_address = user_data.get('start_address', '')
    base_tariff_deeplink = user_data.get('base_tariff_deeplink', '')
    
    # Формируем параметры маршрута
    route_params = []
    if start_address:
        route_params.append(f"start={quote(start_address)}")
    if end_address:
        route_params.append(f"end={quote(end_address)}")
    
    # Объединяем тарифные и маршрутные параметры
    if base_tariff_deeplink:
        if base_tariff_deeplink == "yandextaxi://intercity_main":
            # Для межгорода используем специальную логику
            if route_params:
                deeplink = f"yandextaxi://intercity_main?{'&'.join(route_params)}"
            else:
                deeplink = base_tariff_deeplink
        else:
            # Для остальных тарифов добавляем маршрутные параметры
            if route_params:
                separator = "&" if "?" in base_tariff_deeplink else "?"
                deeplink = f"{base_tariff_deeplink}{separator}{'&'.join(route_params)}"
            else:
                deeplink = base_tariff_deeplink
    else:
        # Если нет базового тарифного диплинка (не должно происходить в новой логике)
        if route_params:
            deeplink = f"yandextaxi://route?{'&'.join(route_params)}"
        else:
            deeplink = "yandextaxi://route"
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_custom_deeplink)
async def process_custom_deeplink(message: types.Message, state: FSMContext):
    """Обработка пользовательского диплинка"""
    deeplink = message.text.strip()
    
    if deeplink == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))

    if not deeplink.startswith(scheme_prefix):
        await message.answer(f"❌ Диплинк должен начинаться с '{scheme_prefix}'. Попробуй ещё раз:")
        return
    
    # Проверяем наличие параметра href и автоматически кодируем его при необходимости
    if "href=" in deeplink:
        try:
            # Извлекаем часть после scheme://
            deeplink_part = deeplink[len(scheme_prefix):]
            
            # Ищем позицию href= в диплинке
            href_pos = deeplink_part.find("href=")
            if href_pos != -1:
                # Разделяем на части: до href= и после href=
                before_href = deeplink_part[:href_pos]
                href_value = deeplink_part[href_pos + 5:]  # все после "href="
                
                # Проверяем, нуждается ли значение href в кодировании
                needs_encoding = any(char in href_value for char in ['%20', '%3A', '%2F', '%3F', '%26', '%3D'])
                
                # Если значение содержит спецсимволы и не закодировано, кодируем его
                if not needs_encoding and any(char in href_value for char in [' ', ':', '/', '?', '&', '=']):
                    encoded_href = quote(href_value)
                    
                    # Пересобираем диплинк
                    deeplink = f"{scheme_prefix}{before_href}href={encoded_href}"
                        
        except Exception as e:
            await message.answer("❌ Ошибка при обработке диплинка. Попробуй ещё раз:")
            return
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_promo_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    """Обработка промокода"""
    promo_code = message.text.strip()
    
    if promo_code == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    if not promo_code:
        await message.answer("❌ Промокод не может быть пустым. Попробуй ещё раз:")
        return
    
    # URL-кодируем промокод
    encoded_promo_code = quote(promo_code)
    
    # Формируем диплинк с промокодом
    deeplink = f"yandextaxi://addpromocode?code={encoded_promo_code}"
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    """Обработка выбора тарифа"""
    tariff_map = {
        "Эконом": "yandextaxi://route?tariffClass=econom",
        "Комфорт": "yandextaxi://route?tariffClass=comfortplus",
        "Комфорт+": "yandextaxi://route?tariffClass=business",
        "Бизнес": "yandextaxi://route?tariffClass=vip&vertical=ultima",
        "Грузовой": "yandextaxi://route?tariffClass=cargo",
        "Детский": "yandextaxi://route?tariffClass=child_tariff",
        "Межгород": "yandextaxi://intercity_main"
    }
    
    tariff_name = message.text.strip()
    
    if tariff_name == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    if tariff_name == "Свой тариф":
        await prompt_custom_tariff(message)
        return
    
    if tariff_name not in tariff_map:
        await message.answer("❌ Пожалуйста, выбери один из предложенных тарифов.")
        return
    
    base_deeplink = tariff_map[tariff_name]
    await state.update_data(base_tariff_deeplink=base_deeplink)
    
    await prompt_route_start(message)


@dp.message_handler(state=LinkBuilder.waiting_for_custom_tariff)
async def process_custom_tariff(message: types.Message, state: FSMContext):
    """Обработка кода пользовательского тарифа"""
    tariff_code = message.text.strip()
    
    if tariff_code == BACK_BUTTON_TEXT:
        await prompt_tariff(message)
        return

    if not tariff_code:
        await message.answer("❌ Код тарифа не может быть пустым. Попробуй ещё раз:")
        return
    
    # URL-кодируем код тарифа
    encoded_tariff_code = quote(tariff_code)
    
    # Формируем базовый диплинк с кодом тарифа
    base_deeplink = f"yandextaxi://route?tariffClass={encoded_tariff_code}"
    
    await state.update_data(base_tariff_deeplink=base_deeplink)
    
    await prompt_route_start(message)


@dp.message_handler(state=LinkBuilder.waiting_for_banner_id)
async def process_banner_id(message: types.Message, state: FSMContext):
    """Обработка ID баннера"""
    banner_id = message.text.strip()
    
    if banner_id == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    if not banner_id:
        await message.answer("❌ ID баннера не может быть пустым. Попробуй ещё раз:")
        return
    
    # URL-кодируем ID баннера
    encoded_banner_id = quote(banner_id)
    
    # Формируем диплинк с ID баннера
    deeplink = f"yandextaxi://banner?id={encoded_banner_id}"
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


async def ask_desktop_url(message: types.Message, state: FSMContext):
    """Запрос URL для десктопа"""
    await message.answer(
        "💻 Введи URL для открытия с десктопа (опционально).\n"
        "Или нажми 'Пропустить', если не нужен:",
        reply_markup=keyboard_skip_back()
    )
    await LinkBuilder.waiting_for_desktop_url.set()


@dp.message_handler(state=LinkBuilder.waiting_for_desktop_url)
async def process_desktop_url(message: types.Message, state: FSMContext):
    """Обработка URL для десктопа"""
    desktop_url = message.text.strip()
    
    if desktop_url == BACK_BUTTON_TEXT:
        user_data = await state.get_data()
        action_type = user_data.get('action_type')
        base_tariff_deeplink = user_data.get('base_tariff_deeplink')
        
        if action_type == "Тариф" and base_tariff_deeplink:
            await prompt_route_end(message)
            return
        
        if action_type == "Промокод":
            await prompt_promo_code(message)
            return
        
        if action_type == "Баннер":
            await prompt_banner_id(message)
            return
        
        if action_type == "Свой диплинк":
            await prompt_custom_deeplink(message, state)
            return

        if action_type == "Сервис":
            await prompt_service(message)
            return
        
        await prompt_action_type_with_state(message, state)
        return

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
    shortener_url = f"https://go-admin-frontend.taxi.tst.yandex-team.ru/adjust?url={encoded_link}"
    
    # Создаем ссылку на статистику
    today = datetime.now().strftime('%Y%m%d')
    campaign_value = f'{today}_bot'
    adgroup_value = transliterate_to_latin(user_data.get('campaign_name', ''))
    
    # Кодируем параметры для ссылки на статистику
    encoded_campaign = quote(f'"{campaign_value}"')
    encoded_adgroup = quote(f'"{adgroup_value}"')
    
    app_name = user_data.get('app', GO_APP_NAME)
    app_tokens_by_app = {
        GO_APP_NAME: "%2255ug2ntb3uzf%22%2C%22cs75zaz26h8x%22",
        # Заглушки для токенов других приложений — будут заменены позже
        "Еда": "%22TODO_EATS_APP_TOKEN%22"
    }
    app_tokens = app_tokens_by_app.get(app_name, "%22TODO_APP_TOKEN%22")
    
    stats_url = (
        "https://suite.adjust.com/datascape/report?"
        f"app_token__in={app_tokens}&"
        "utc_offset=%2B00%3A00&reattributed=all&attribution_source=dynamic&"
        "attribution_type=all&ad_spend_mode=network&date_period=-7d%3A-1d&"
        "cohort_maturity=immature&sandbox=false&assisting_attribution_type=all&"
        "ironsource_mode=ironsource&digital_turbine_mode=digital_turbine&"
        "network__in=%22Promo+%28True+Link%29%22%2C%22Promo+Instant+Reattribution+%28True+Link%29%22%2C%22Promo+Instant+Reattribution+Temporary+30+%28True+Link%29%22%2C%22Promo+Temporary+30+%28True+Link%29%22&"
        "dimensions=channel%2Ccampaign_network%2Cadgroup_network&"
        "metrics=attribution_clicks%2Cinstalls%2Creattributions%2Csuccess_first_order_events&"
        "sort=-installs&installs__column_heatmap=%23C19CFF&is_report_setup_open=true&"
        f"campaign_network__in__column={encoded_campaign}&"
        f"adgroup_network__in__column={encoded_adgroup}"
    )
    
    await message.answer(
        f"🎉 Готово! Твоя ссылка:\n\n"
        f"`{final_link}`\n\n"
        f"📋 Скопируй ссылку выше и используй в своей кампании!\n\n"
        f"📱 Для использования в SMS или QR-кодах рекомендуется сократить ссылку:\n"
        f"[Перейти к сокращению ссылки]({shortener_url})\n\n"
        f"📊 Для просмотра статистики переходов и установок:\n"
        f"[Открыть статистику в Adjust]({stats_url})\n\n"
        f"Чтобы создать новую ссылку, отправь /start",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    await state.finish()


@dp.message_handler()
async def handle_other_messages(message: types.Message):
    """Обработка прочих сообщений"""
    await message.answer(
        "🤖 Привет! Чтобы создать ссылку, отправь команду /start"
    )


if __name__ == '__main__':
    print("🚀 Запуск бота...")
    executor.start_polling(dp, skip_updates=True)