import os
import re
import logging
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, parse_qsl, unquote
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
OPEN_APP_GO = "Просто открыть приложение"
OPEN_APP_OTHER = "Просто открыть приложение"

APP_ORDER = [
    "Драйв",
    "Еда",
    "Про",
    "Go",
    "Yango",
    "Yango Pro"
]
APP_CATALOG = {
    "Драйв": {"scheme": "yandexdrive://", "base_url": "https://drive.go.link/"},
    "Еда": {"scheme": "eda.yandex://", "base_url": "https://eats.go.link/"},
    "Про": {"scheme": "taximeter://", "base_url": "https://lecj.adj.st/"},
    "Go": {"scheme": "yandextaxi://", "base_url": "https://yandex.go.link/"},
    "Yango": {"scheme": "yandexyango://", "base_url": "https://yango.go.link/"},
    "Yango Pro": {"scheme": "taximeter://", "base_url": "https://ubq5.adj.st/"}
}

APP_OPTIONS = APP_ORDER
REATTRIBUTION_OPTIONS = ["Только неактивных от 30 дней", "Реатрибуцировать всех"]
TEMP_ATTR_OPTIONS = ["Без ограничений", "30 дней"]
ACTION_TYPE_OPTIONS = [
    OPEN_APP_GO,
    "Сервис",
    "Промокод",
    "Тариф",
    "Баннер",
    "Свой диплинк"
]
SERVICE_OPTIONS = ["Еда", "Лавка", "Драйв", "Маркет", "Самокаты", "Транспорт"]
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
    waiting_for_eats_tracker_choice = State()
    waiting_for_reattribution = State()
    waiting_for_temporary_attribution = State()
    waiting_for_campaign = State()
    waiting_for_action_type = State()
    waiting_for_service = State()
    waiting_for_eats_option = State()
    waiting_for_eats_shop_url = State()
    waiting_for_eats_collections_url = State()
    waiting_for_eats_service_url_deeplink = State()
    waiting_for_eats_restaurant_url = State()
    waiting_for_eats_url_deeplink = State()
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
    return make_keyboard(APP_OPTIONS, include_back=False)


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


def keyboard_eats_tracker_choice() -> ReplyKeyboardMarkup:
    return make_keyboard(
        ["Настроить атрибуцию", "Partners_new", "SMM", "dineout"],
        include_back=True
    )


def keyboard_eats_options() -> ReplyKeyboardMarkup:
    return make_keyboard(
        ["Главная Еды", "Магазин", "Коллекции", "Диплинк из URL"],
        include_back=True
    )


def get_app_name_or_default(app_name: Optional[str]) -> str:
    if app_name in APP_CATALOG:
        return app_name
    return APP_ORDER[0] if APP_ORDER else GO_APP_NAME


def get_app_scheme(app_name: Optional[str]) -> str:
    app_name = get_app_name_or_default(app_name)
    return APP_CATALOG.get(app_name, APP_CATALOG[GO_APP_NAME])["scheme"]


def get_app_base_url(app_name: Optional[str]) -> str:
    app_name = get_app_name_or_default(app_name)
    return APP_CATALOG.get(app_name, APP_CATALOG[GO_APP_NAME])["base_url"]


def get_adj_t_map(app_name: Optional[str]) -> Dict[tuple, str]:
    app_name = get_app_name_or_default(app_name)
    if app_name == GO_APP_NAME:
        return {
            ('Реатрибуцировать всех', 'Без ограничений'): '1pj8ktrc_1pksjytf',
            ('Только неактивных от 30 дней', 'Без ограничений'): '1md8ai4n_1mztz3nz',
            ('Реатрибуцировать всех', '30 дней'): '1p5j0f1z_1pk9ju0y',
            ('Только неактивных от 30 дней', '30 дней'): '1pi2vjj3_1ppvctfa'
        }
    if app_name == "Драйв":
        return {
            ('Только неактивных от 30 дней', 'Без ограничений'): '1w1fyjuh',
            ('Только неактивных от 30 дней', '30 дней'): '1w6rk3g5',
            ('Реатрибуцировать всех', 'Без ограничений'): '1w1h2sce',
            ('Реатрибуцировать всех', '30 дней'): '1w1k1t8b'
        }
    if app_name == "Еда":
        return {
            ('Реатрибуцировать всех', 'Без ограничений'): '1wj02w0e_1woudcyr',
            ('Только неактивных от 30 дней', 'Без ограничений'): '1w72129e_1ww1am8e',
            ('Реатрибуцировать всех', '30 дней'): '1w1uhauh_1w3dtcvs',
            ('Только неактивных от 30 дней', '30 дней'): '1wwnx9c4_1wybzoum'
        }
    if app_name == "Про":
        return {
            ('Только неактивных от 30 дней', 'Без ограничений'): '1w1w0cie_1wf70eky',
            ('Только неактивных от 30 дней', '30 дней'): '1whu80dy_1wtdlfwn',
            ('Реатрибуцировать всех', 'Без ограничений'): '1w7uoyoq_1wsa2db8',
            ('Реатрибуцировать всех', '30 дней'): '1w7ztrws_1wqmugs1'
        }
    if app_name == "Yango":
        return {
            ('Только неактивных от 30 дней', 'Без ограничений'): '1wrqmlfd_1wtbr2vt',
            ('Только неактивных от 30 дней', '30 дней'): '1w3dkzxf_1wksmxnr',
            ('Реатрибуцировать всех', 'Без ограничений'): '1wlyrbe7_1woa6n8p',
            ('Реатрибуцировать всех', '30 дней'): '1w6zxhcl_1wfkbjtw'
        }
    if app_name == "Yango Pro":
        return {
            ('Только неактивных от 30 дней', 'Без ограничений'): '1wcen01x_1wh11pd5',
            ('Только неактивных от 30 дней', '30 дней'): '1w59mp9k_1wkp0jy5',
            ('Реатрибуцировать всех', 'Без ограничений'): '1w31vlxu_1w3aa34h',
            ('Реатрибуцировать всех', '30 дней'): '1wxd0aln_1wzdqopt'
        }
    # Заглушки для трекеров остальных приложений — будут заменены позже
    return {
        ('Реатрибуцировать всех', 'Без ограничений'): 'TODO_TRACKER_1',
        ('Только неактивных от 30 дней', 'Без ограничений'): 'TODO_TRACKER_2',
        ('Реатрибуцировать всех', '30 дней'): 'TODO_TRACKER_3',
        ('Только неактивных от 30 дней', '30 дней'): 'TODO_TRACKER_4'
    }


def get_action_type_options(app_name: Optional[str]) -> List[str]:
    app_name = get_app_name_or_default(app_name)
    if app_name == GO_APP_NAME:
        return ACTION_TYPE_OPTIONS
    if app_name == "Yango":
        return [OPEN_APP_OTHER, "Промокод", "Тариф", "Баннер", "Свой диплинк"]
    if app_name == "Еда":
        return [OPEN_APP_OTHER, "Ресторан", "Диплинк из URL", "Свой диплинк"]
    return [OPEN_APP_OTHER, "Свой диплинк"]


def get_open_app_deeplink(app_name: Optional[str]) -> str:
    app_name = get_app_name_or_default(app_name)
    scheme_prefix = get_app_scheme(app_name)
    if app_name in ["Про", "Yango Pro"]:
        return f"{scheme_prefix}screen/main?"
    return scheme_prefix


def keyboard_action_type_for_app(app_name: Optional[str]) -> ReplyKeyboardMarkup:
    return make_keyboard(get_action_type_options(app_name), include_back=True)


def build_reattribution_text(app_name: Optional[str] = None) -> str:
    base_question = (
        "❓ Если у пользователя уже было приложение и он активен, нужно ли его "
        "атрибуцировать к этой ссылке?"
    )
    if app_name:
        return f"✅ Делаем ссылку для приложения {app_name}.\n\n{base_question}"
    return base_question


def build_temp_attr_text() -> str:
    return "⏰ Сколько пользователь должен оставаться в трекере после последнего контакта?"


async def prompt_app(message: types.Message) -> None:
    await message.answer(
        "📱 Для какого приложения нужно создать ссылку?",
        reply_markup=keyboard_app()
    )
    await LinkBuilder.waiting_for_app.set()


async def prompt_eats_tracker_choice(message: types.Message) -> None:
    await message.answer(
        "Настроить атрибуцию или использовать существующий трекер?",
        reply_markup=keyboard_eats_tracker_choice()
    )
    await LinkBuilder.waiting_for_eats_tracker_choice.set()


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


async def prompt_eats_option(message: types.Message) -> None:
    await message.answer(
        "🍔 Что открыть в Еде?",
        reply_markup=keyboard_eats_options()
    )
    await LinkBuilder.waiting_for_eats_option.set()


async def prompt_eats_shop_url(message: types.Message) -> None:
    await message.answer(
        "🛒 Введи ссылку на магазин (eda.yandex или eats.yandex.com, и в пути retail):",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_eats_shop_url.set()


async def prompt_eats_collections_url(message: types.Message) -> None:
    await message.answer(
        "🧾 Введи ссылку на коллекцию (eda.yandex и в пути /collections/):",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_eats_collections_url.set()


async def prompt_eats_service_url_deeplink(message: types.Message) -> None:
    await message.answer(
        "🔗 Введи URL (eda.yandex или eats.yandex.com, язык в пути игнорируется):",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_eats_service_url_deeplink.set()


async def prompt_eats_restaurant_url(message: types.Message) -> None:
    await message.answer(
        "🍽 Введи ссылку на ресторан (eda.yandex и в пути /r/):",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_eats_restaurant_url.set()


async def prompt_eats_url_deeplink(message: types.Message) -> None:
    await message.answer(
        "🔗 Введи URL (обязательно eda.yandex в домене). Из него будет создан диплинк:",
        reply_markup=keyboard_back_only()
    )
    await LinkBuilder.waiting_for_eats_url_deeplink.set()


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


def normalize_desktop_url(desktop_url: Optional[str], campaign_value: str, adgroup_value: str) -> Optional[str]:
    if not desktop_url:
        return None

    parsed_url = urlparse(desktop_url)
    query_params = parse_qs(parsed_url.query, keep_blank_values=True)

    if 'utm_source' not in query_params:
        query_params['utm_source'] = [campaign_value]

    if 'utm_campaign' not in query_params:
        query_params['utm_campaign'] = [adgroup_value]

    query_parts = []
    for key, values in query_params.items():
        for value in values:
            if value:
                query_parts.append(f"{key}={quote(str(value))}")
            else:
                query_parts.append(key)

    if query_parts:
        new_query = '&'.join(query_parts)
        desktop_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?{new_query}"
        if parsed_url.fragment:
            desktop_url += f"#{parsed_url.fragment}"

    return desktop_url


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
    
    adj_t_override = user_data.get('adj_t_override')
    if adj_t_override:
        adj_t = adj_t_override
    else:
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
    desktop_url = normalize_desktop_url(user_data.get('desktop_url'), campaign_value, adgroup_value)
    if desktop_url:
        params['adj_fallback'] = quote(desktop_url)
        params['adj_redirect_macos'] = quote(desktop_url)
    
    # Строим URL
    param_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    
    # Определяем разделитель - ? если в deeplink нет параметров, & если есть
    separator = '&' if '?' in deeplink else '?'
    final_url = f"{base_url}{deeplink}{separator}{param_string}"
    
    return final_url


def build_adjust_app_link(user_data: Dict[str, Any]) -> str:
    """Построение ссылки app.adjust.com"""
    app_name = user_data.get('app', GO_APP_NAME)
    scheme_prefix = get_app_scheme(app_name)
    deeplink = user_data.get('deeplink', '')
    if not deeplink.startswith(scheme_prefix):
        deeplink = f"{scheme_prefix}{deeplink}"

    today = datetime.now().strftime('%Y%m%d')
    campaign_value = f'{today}_bot'
    adgroup_value = transliterate_to_latin(user_data.get('campaign_name', ''))

    reattribution = user_data.get('reattribution', 'Только неактивных от 30 дней')
    temporary_attribution = user_data.get('temporary_attribution', 'Без ограничений')
    adj_t_override = user_data.get('adj_t_override')
    if adj_t_override:
        adj_t = adj_t_override
    else:
        adj_t_map = get_adj_t_map(app_name)
        adj_t = adj_t_map.get(
            (reattribution, temporary_attribution),
            next(iter(adj_t_map.values()))
        )

    params = {
        'campaign': campaign_value,
        'adgroup': adgroup_value,
        'deeplink': quote(deeplink)
    }

    desktop_url = normalize_desktop_url(user_data.get('desktop_url'), campaign_value, adgroup_value)
    if desktop_url:
        params['fallback'] = quote(desktop_url)
        params['redirect_macos'] = quote(desktop_url)

    param_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    return f"https://app.adjust.com/{adj_t}?{param_string}"


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

    if app_name == "Еда":
        await prompt_eats_tracker_choice(message)
        return

    await prompt_reattribution(message, app_name=app_name)


@dp.message_handler(state=LinkBuilder.waiting_for_eats_tracker_choice)
async def process_eats_tracker_choice(message: types.Message, state: FSMContext):
    """Обработка выбора трекера для Еды"""
    choice = message.text.strip()

    if choice == BACK_BUTTON_TEXT:
        await prompt_app(message)
        return

    tracker_map = {
        "Partners_new": "1c5h66r3_1cye0uen",
        "SMM": "jrzfg8i_wg988s5",
        "dineout": "1tfiic8a_1tiyod4w"
    }

    if choice == "Настроить атрибуцию":
        await prompt_reattribution(message, app_name="Еда")
        return

    if choice in tracker_map:
        await state.update_data(adj_t_override=tracker_map[choice])
        await prompt_campaign(message)
        return

    await message.answer(
        "❌ Пожалуйста, выбери один из предложенных вариантов.",
        reply_markup=keyboard_eats_tracker_choice()
    )


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

    if action in [OPEN_APP_GO, OPEN_APP_OTHER]:
        await state.update_data(deeplink=get_open_app_deeplink(app_name))
        await ask_desktop_url(message, state)
        
    elif action == "Сервис":
        await prompt_service(message)
        
    elif action == "Промокод":
        await prompt_promo_code(message)
        
    elif action == "Тариф":
        await prompt_tariff(message)
        
    elif action == "Баннер":
        await prompt_banner_id(message)
        
    elif action == "Ресторан":
        await prompt_eats_restaurant_url(message)

    elif action == "Диплинк из URL":
        await prompt_eats_url_deeplink(message)

    elif action == "Свой диплинк":
        await prompt_custom_deeplink(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_service)
async def process_service(message: types.Message, state: FSMContext):
    """Обработка выбора сервиса"""
    # Специальные диплинки для некоторых сервисов
    special_service_map = {
        "Самокаты": "yandextaxi://scooters",
        "Транспорт": "yandextaxi://masstransit"
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

    if service_name == "Еда":
        await prompt_eats_option(message)
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


@dp.message_handler(state=LinkBuilder.waiting_for_eats_option)
async def process_eats_option(message: types.Message, state: FSMContext):
    """Обработка выбора опции Еды"""
    eats_option = message.text.strip()

    if eats_option == BACK_BUTTON_TEXT:
        await prompt_service(message)
        return

    if eats_option == "Главная Еды":
        await state.update_data(deeplink="yandextaxi://external?service=eats")
        await ask_desktop_url(message, state)
        return

    if eats_option == "Магазин":
        await prompt_eats_shop_url(message)
        return

    if eats_option == "Коллекции":
        await prompt_eats_collections_url(message)
        return

    if eats_option == "Диплинк из URL":
        await prompt_eats_service_url_deeplink(message)
        return

    await message.answer(
        "❌ Пожалуйста, выбери один из предложенных вариантов.",
        reply_markup=keyboard_eats_options()
    )


def build_eats_shop_deeplink(shop_url: str) -> Optional[str]:
    try:
        parsed = urlparse(shop_url)
    except Exception:
        return None

    host = parsed.netloc.lower()
    if not (host.startswith("eda.yandex") or host.startswith("eats.yandex.com")):
        return None

    path = parsed.path or ""
    if "retail" not in path:
        return None

    href = path.lstrip("/")
    if parsed.query:
        href = f"{href}?{parsed.query}"

    return f"yandextaxi://external?service=eats&href={quote(href)}"


def build_eats_collections_deeplink(collections_url: str) -> Optional[str]:
    try:
        parsed = urlparse(collections_url)
    except Exception:
        return None

    host = parsed.netloc.lower()
    if not host.startswith("eda.yandex"):
        return None

    path = parsed.path or ""
    if "/collections" not in path:
        return None

    href = path.lstrip("/")
    if parsed.query:
        href = f"{href}?{parsed.query}"

    return f"yandextaxi://external?service=eats&href={quote(href)}"


def build_eats_restaurant_deeplink(restaurant_url: str) -> Optional[str]:
    try:
        parsed = urlparse(restaurant_url)
    except Exception:
        return None

    host = parsed.netloc.lower()
    if not host.startswith("eda.yandex"):
        return None

    if "/r/" not in parsed.path:
        return None

    query_params = parse_qs(parsed.query)
    place_slug = query_params.get("placeSlug", [None])[0]
    if not place_slug:
        return None

    return f"eda.yandex://restaurant/{place_slug}"


def extract_eats_tail_from_url(source_url: str) -> Optional[str]:
    try:
        parsed = urlparse(source_url)
    except Exception:
        return None

    host = parsed.netloc.lower()
    if not (host.startswith("eda.yandex") or host.startswith("eats.yandex.com")):
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and len(segments[0]) == 2:
        segments = segments[1:]
    if not segments:
        return None

    path = "/".join(segments)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if query_items:
        query_parts = []
        for key, value in query_items:
            encoded_value = quote(value, safe="") if value else ""
            query_parts.append(f"{key}={encoded_value}")
        query = "&".join(query_parts)
        return f"{path}?{query}"
    return path


def build_eats_url_deeplink(source_url: str) -> Optional[str]:
    tail = extract_eats_tail_from_url(source_url)
    if not tail:
        return None
    return f"eda.yandex://{tail}"


@dp.message_handler(state=LinkBuilder.waiting_for_eats_shop_url)
async def process_eats_shop_url(message: types.Message, state: FSMContext):
    """Обработка ссылки на магазин Еды"""
    shop_url = message.text.strip()

    if shop_url == BACK_BUTTON_TEXT:
        await prompt_eats_option(message)
        return

    deeplink = build_eats_shop_deeplink(shop_url)
    if not deeplink:
        await message.answer(
            "❌ Нужна ссылка на магазин Еды: домен eda.yandex или eats.yandex.com, "
            "и в пути должен быть retail. Попробуй ещё раз:"
        )
        return

    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_eats_collections_url)
async def process_eats_collections_url(message: types.Message, state: FSMContext):
    """Обработка ссылки на коллекцию Еды"""
    collections_url = message.text.strip()

    if collections_url == BACK_BUTTON_TEXT:
        await prompt_eats_option(message)
        return

    deeplink = build_eats_collections_deeplink(collections_url)
    if not deeplink:
        await message.answer(
            "❌ Нужна ссылка на коллекцию Еды: домен eda.yandex и путь /collections. "
            "Попробуй ещё раз:"
        )
        return

    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_eats_service_url_deeplink)
async def process_eats_service_url_deeplink(message: types.Message, state: FSMContext):
    """Обработка URL для диплинка сервиса Еда в Go"""
    source_url = message.text.strip()

    if source_url == BACK_BUTTON_TEXT:
        await prompt_eats_option(message)
        return

    tail = extract_eats_tail_from_url(source_url)
    if not tail:
        await message.answer(
            "❌ Нужен URL с доменом eda.yandex (любая зона) или eats.yandex.com. "
            "Язык в пути игнорируется. Попробуй ещё раз:"
        )
        return

    deeplink = f"yandextaxi://external?service=eats&href={quote(tail)}"
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_eats_restaurant_url)
async def process_eats_restaurant_url(message: types.Message, state: FSMContext):
    """Обработка ссылки на ресторан Еды"""
    restaurant_url = message.text.strip()

    if restaurant_url == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    deeplink = build_eats_restaurant_deeplink(restaurant_url)
    if not deeplink:
        await message.answer(
            "❌ Нужна ссылка на ресторан Еды: домен eda.yandex и в пути /r/, "
            "и параметр placeSlug. Попробуй ещё раз:"
        )
        return

    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_eats_url_deeplink)
async def process_eats_url_deeplink(message: types.Message, state: FSMContext):
    """Обработка URL для диплинка Еды"""
    source_url = message.text.strip()

    if source_url == BACK_BUTTON_TEXT:
        await prompt_action_type_with_state(message, state)
        return

    deeplink = build_eats_url_deeplink(source_url)
    if not deeplink:
        await message.answer(
            "❌ Нужен URL с доменом eda.yandex (любая зона) или eats.yandex.com. "
            "Язык в пути игнорируется. Попробуй ещё раз:"
        )
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
    scheme_prefix = get_app_scheme(user_data.get("app"))
    
    # Формируем параметры маршрута
    route_params = []
    if start_address:
        route_params.append(f"start={quote(start_address)}")
    if end_address:
        route_params.append(f"end={quote(end_address)}")
    
    # Объединяем тарифные и маршрутные параметры
    if base_tariff_deeplink:
        if base_tariff_deeplink == f"{scheme_prefix}intercity_main":
            # Для межгорода используем специальную логику
            if route_params:
                deeplink = f"{scheme_prefix}intercity_main?{'&'.join(route_params)}"
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
            deeplink = f"{scheme_prefix}route?{'&'.join(route_params)}"
        else:
            deeplink = f"{scheme_prefix}route"
    
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
    
    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))

    # URL-кодируем промокод
    encoded_promo_code = quote(promo_code)
    
    # Формируем диплинк с промокодом
    deeplink = f"{scheme_prefix}addpromocode?code={encoded_promo_code}"
    
    await state.update_data(deeplink=deeplink)
    await ask_desktop_url(message, state)


@dp.message_handler(state=LinkBuilder.waiting_for_tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    """Обработка выбора тарифа"""
    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))
    tariff_map = {
        "Эконом": f"{scheme_prefix}route?tariffClass=econom",
        "Комфорт": f"{scheme_prefix}route?tariffClass=comfortplus",
        "Комфорт+": f"{scheme_prefix}route?tariffClass=business",
        "Бизнес": f"{scheme_prefix}route?tariffClass=vip&vertical=ultima",
        "Грузовой": f"{scheme_prefix}route?tariffClass=cargo",
        "Детский": f"{scheme_prefix}route?tariffClass=child_tariff",
        "Межгород": f"{scheme_prefix}intercity_main"
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
    
    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))

    # URL-кодируем код тарифа
    encoded_tariff_code = quote(tariff_code)
    
    # Формируем базовый диплинк с кодом тарифа
    base_deeplink = f"{scheme_prefix}route?tariffClass={encoded_tariff_code}"
    
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
    
    user_data = await state.get_data()
    scheme_prefix = get_app_scheme(user_data.get("app"))

    # URL-кодируем ID баннера
    encoded_banner_id = quote(banner_id)
    
    # Формируем диплинк с ID баннера
    deeplink = f"{scheme_prefix}banner?id={encoded_banner_id}"
    
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
    alt_link = build_adjust_app_link(user_data)
    
    # Создаём ссылку для сокращения
    encoded_link = quote(final_link)
    shortener_url = f"https://go-admin-frontend.taxi.yandex-team.ru/adjust?url={encoded_link}"
    
    # Создаем ссылку на статистику
    today = datetime.now().strftime('%Y%m%d')
    campaign_value = f'{today}_bot'
    adgroup_value = transliterate_to_latin(user_data.get('campaign_name', ''))
    
    # Кодируем параметры для ссылки на статистику
    encoded_campaign = quote(f'"{campaign_value}"')
    encoded_adgroup = quote(f'"{adgroup_value}"')
    
    stats_url = (
        "https://suite.adjust.com/datascape/report?"
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
        f"🔗 [Альтернативная ссылка]({alt_link})\n\n"
        f"📋 Скопируй ссылку выше и используй в своей кампании!\n\n"
        f"📱 Для использования в SMS или QR-кодах рекомендуется сократить ссылку:\n"
        f"[Перейти к сокращению ссылки]({shortener_url})\n\n"
        f"📊 Для просмотра статистики переходов и установок:\n"
        f"[Открыть статистику в Adjust]({stats_url})\n\n"
        f"🐞 Баги и пожелания: [igbelousov](https://t.me/ibelousov)\n\n"
        f"Чтобы создать новую ссылку, отправь /start",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    
    await state.finish()


@dp.message_handler()
async def handle_other_messages(message: types.Message):
    """Обработка прочих сообщений"""
    await message.answer(
        "🤖 Чтобы создать ссылку, отправь команду /start"
    )


if __name__ == '__main__':
    print("🚀 Запуск бота...")
    executor.start_polling(dp, skip_updates=True)