import asyncio
import logging
import aiohttp
import math
import os
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = '8483372961:AAGViQ7od5qye9DwM8C_pQIFOeww_3e9_-s'

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ADMIN_IDS = [1730848079, 713476634]
CHELYABINSK_CENTER = (55.159897, 61.402554)

PRICE_PHOTOS = {
    'tech_plan': '(Прайс тех.план).JPG',
    'acts': '(Прайс Акты, справки).JPG',
    'surveying': '(Прайс межевание).JPG',
    'tech_passport': '(Прайс тех.паспорт).JPG'
}


class Form(StatesGroup):
    waiting_for_service = State()
    waiting_for_purpose = State()
    waiting_for_bank = State()
    waiting_for_mortgage_purpose = State()
    waiting_for_object_type = State()
    waiting_for_report_type = State()
    waiting_for_flood_rooms = State()
    waiting_for_address = State()
    waiting_for_date = State()
    waiting_for_documents = State()
    waiting_for_insurance_type = State()
    waiting_for_insurance_coverage = State()
    waiting_for_insurance_object = State()
    waiting_for_mortgage_balance = State()
    waiting_for_insurance_documents = State()
    waiting_for_bti_service = State()
    waiting_for_bti_object_type = State()
    waiting_for_bti_surveying_service = State()
    waiting_for_bti_acts_service = State()
    waiting_for_expertise_type = State()
    waiting_for_expertise_stage = State()
    waiting_for_expertise_object = State()
    waiting_for_expertise_status = State()
    waiting_for_expertise_tasks = State()
    waiting_for_expertise_description = State()
    waiting_for_expertise_photos = State()
    waiting_for_acceptance_state = State()
    waiting_for_acceptance_material = State()
    waiting_for_acceptance_area = State()
    waiting_for_inspection_object = State()
    waiting_for_inspection_area = State()
    waiting_for_inspection_material = State()
    waiting_for_inspection_finish = State()
    waiting_for_thermal_object = State()
    waiting_for_thermal_area = State()
    waiting_for_deals_service = State()


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def is_in_chelyabinsk(full_address: str) -> bool:
    """Проверяет, находится ли адрес в городе Челябинск"""
    if not full_address:
        return False

    address_lower = full_address.lower()

    # Проверяем, что это именно город Челябинск, а не область
    if 'челябинск,' in address_lower or 'челябинск ' in address_lower:
        # Исключаем Челябинскую область
        if 'челябинская область' in address_lower and 'челябинск,' not in address_lower:
            return False
        return True

    return False


async def geocode_address(address: str):
    try:
        formatted_address = format_address_for_geocoder(address)
        async with aiohttp.ClientSession() as session:
            url = "https://geocode-maps.yandex.ru/1.x/"
            params = {
                "apikey": "61f30bb9-04d7-4eb9-8636-908c6f611e4c",
                "geocode": formatted_address,
                "format": "json",
                "results": 1
            }
            logger.info(f"Geocoding: {formatted_address}")
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        feature_member = data['response']['GeoObjectCollection']['featureMember']
                        if feature_member:
                            geo_object = feature_member[0]['GeoObject']
                            pos = geo_object['Point']['pos']
                            lon, lat = map(float, pos.split())
                            full_address = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get(
                                'text', 'Неизвестно')
                            logger.info(f"Success: {full_address} -> ({lat}, {lon})")
                            return lat, lon, full_address
                    except (KeyError, IndexError, ValueError) as e:
                        logger.error(f"Parse error: {e}")
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
    return None, None, None


def format_address_for_geocoder(address: str) -> str:
    address_lower = address.lower()
    cities = ['челябинск', 'миасс', 'златоуст', 'копейск', 'магнитогорск',
              'сатка', 'озёрск', 'трёхгорный', 'южноуральск', 'коркино']
    city_in_address = any(city in address_lower for city in cities)
    if not city_in_address:
        return f"Челябинск, {address}"
    return address


async def send_to_admins(text: str, user_info: str = None):
    message_text = f"🔔 <b>НОВАЯ ЗАЯВКА</b>\n\n{text}"
    if user_info:
        message_text += f"\n\n👤 <b>От пользователя:</b>\n{user_info}"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send message to admin {admin_id}: {e}")


def get_user_info(user) -> str:
    info = f"ID: {user.id}\n"
    if user.username:
        info += f"Username: @{user.username}\n"
    info += f"Имя: {user.first_name or 'Не указано'}"
    if user.last_name:
        info += f" {user.last_name}"
    return info


def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back")]])


def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Оценка недвижимости", callback_data="service_1")],
        [InlineKeyboardButton(text="💧 Оценка ущерба после затопления", callback_data="service_2")],
        [InlineKeyboardButton(text="📋 БТИ / Кадастр / Межевание", callback_data="service_3")],
        [InlineKeyboardButton(text="🔨 Строительно-техническая экспертиза / Обследования", callback_data="service_4")],
        [InlineKeyboardButton(text="🛡️ Ипотечное страхование", callback_data="service_5")],
        [InlineKeyboardButton(text="🏢 Сделки с недвижимостью", callback_data="service_6")],
        [InlineKeyboardButton(text="✉️ Написать нам напрямую", url="https://t.me/+79080415241")]
    ])


def get_bti_services_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Выписка из технического паспорта", callback_data="bti_1")],
        [InlineKeyboardButton(text="📋 Технический паспорт", callback_data="bti_2")],
        [InlineKeyboardButton(text="📐 Технический план", callback_data="bti_3")],
        [InlineKeyboardButton(text="🗺️ Межевание (земля)", callback_data="bti_4")],
        [InlineKeyboardButton(text="📑 Акты, справки", callback_data="bti_5")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_bti_object_types_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира", callback_data="bti_object_flat")],
        [InlineKeyboardButton(text="🏡 Жилой дом", callback_data="bti_object_house")],
        [InlineKeyboardButton(text="🏢 Нежилое помещение", callback_data="bti_object_nonres")],
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="bti_object_garage")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_tech_plan_options():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="tech_plan_price")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_tech_plan_objects():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира, комната", callback_data="tech_plan_obj_1")],
        [InlineKeyboardButton(text="🏡 Жилой дом/садовый дом/таунхаус", callback_data="tech_plan_obj_2")],
        [InlineKeyboardButton(text="🏢 Нежилое помещение", callback_data="tech_plan_obj_3")],
        [InlineKeyboardButton(text="🏭 Нежилое здание", callback_data="tech_plan_obj_4")],
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="tech_plan_obj_5")],
        [InlineKeyboardButton(text="🔀 Раздел дома", callback_data="tech_plan_obj_6")],
        [InlineKeyboardButton(text="🔗 Раздел/объединение помещений", callback_data="tech_plan_obj_7")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_surveying_options():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="surveying_price")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_surveying_services():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📏 Уточнение границ зем. участка", callback_data="surv_serv_1")],
        [InlineKeyboardButton(text="✂️ Раздел/объединение участка", callback_data="surv_serv_2")],
        [InlineKeyboardButton(text="📋 Схема для КУиЗО", callback_data="surv_serv_3")],
        [InlineKeyboardButton(text="🔄 Перераспределение (межевой)", callback_data="surv_serv_4")],
        [InlineKeyboardButton(text="🔄📋 Перераспределение (схема + межевой)", callback_data="surv_serv_5")],
        [InlineKeyboardButton(text="🚗 Схема под гараж", callback_data="surv_serv_6")],
        [InlineKeyboardButton(text="📄 Межевой по распоряжению", callback_data="surv_serv_7")],
        [InlineKeyboardButton(text="⚖️ Межевой для суда", callback_data="surv_serv_8")],
        [InlineKeyboardButton(text="🔒 Межевой на сервитут", callback_data="surv_serv_9")],
        [InlineKeyboardButton(text="➕ Другое", callback_data="surv_serv_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_acts_options():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="acts_price")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_acts_services():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Документы на акт ввода до 1500 кв.м", callback_data="acts_serv_1")],
        [InlineKeyboardButton(text="🚗 На гараж", callback_data="acts_serv_2")],
        [InlineKeyboardButton(text="🗑️ Акт сноса", callback_data="acts_serv_3")],
        [InlineKeyboardButton(text="📍 Справка о местоположении (комната)", callback_data="acts_serv_4")],
        [InlineKeyboardButton(text="💰 Справка о стоимости", callback_data="acts_serv_5")],
        [InlineKeyboardButton(text="📝 Заполнение уведомлений", callback_data="acts_serv_6")],
        [InlineKeyboardButton(text="➕ Другое", callback_data="acts_serv_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_tech_passport_options():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="tech_passport_price")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_expertise_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Строительно-техническая экспертиза", callback_data="expertise_1")],
        [InlineKeyboardButton(text="🏡 Приемка жилого дома от застройщика", callback_data="expertise_2")],
        [InlineKeyboardButton(text="🏠 Техническое обследование перед покупкой", callback_data="expertise_3")],
        [InlineKeyboardButton(text="🌡️ Тепловизионное обследование", callback_data="expertise_4")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_expertise_stage_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚖️ Идёт судебный процесс", callback_data="exp_stage_1")],
        [InlineKeyboardButton(text="📝 Досудебное урегулирование", callback_data="exp_stage_2")],
        [InlineKeyboardButton(text="❓ Затрудняюсь ответить", callback_data="exp_stage_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_expertise_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира", callback_data="exp_obj_1")],
        [InlineKeyboardButton(text="🏡 Жилой дом / коттедж", callback_data="exp_obj_2")],
        [InlineKeyboardButton(text="🏢 Коммерческий объект", callback_data="exp_obj_3")],
        [InlineKeyboardButton(text="🏚️ Кровля", callback_data="exp_obj_4")],
        [InlineKeyboardButton(text="🏗️ Фундамент", callback_data="exp_obj_5")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_expertise_status_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Построен", callback_data="exp_status_1")],
        [InlineKeyboardButton(text="🚧 В процессе строительства", callback_data="exp_status_2")],
        [InlineKeyboardButton(text="🔧 После ремонта / реконструкции", callback_data="exp_status_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_acceptance_state_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔨 Черновая (без отделки)", callback_data="acc_state_1")],
        [InlineKeyboardButton(text="🎨 Предчистовая", callback_data="acc_state_2")],
        [InlineKeyboardButton(text="✨ Чистовая (с отделкой)", callback_data="acc_state_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_acceptance_material_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧱 Кирпич", callback_data="acc_mat_1")],
        [InlineKeyboardButton(text="🏗️ Ж/б панели", callback_data="acc_mat_2")],
        [InlineKeyboardButton(text="🔲 Блочный", callback_data="acc_mat_3")],
        [InlineKeyboardButton(text="🌲 Дерево", callback_data="acc_mat_4")],
        [InlineKeyboardButton(text="➕ Другой", callback_data="acc_mat_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_acceptance_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 150 кв.м", callback_data="acc_area_1")],
        [InlineKeyboardButton(text="150-250 кв.м", callback_data="acc_area_2")],
        [InlineKeyboardButton(text="250-500 кв.м", callback_data="acc_area_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_inspection_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 150 кв.м", callback_data="insp_area_1")],
        [InlineKeyboardButton(text="150-250 кв.м", callback_data="insp_area_2")],
        [InlineKeyboardButton(text="250-350 кв.м", callback_data="insp_area_3")],
        [InlineKeyboardButton(text="свыше 350 кв.м", callback_data="insp_area_4")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_inspection_material_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧱 Кирпич", callback_data="insp_mat_1")],
        [InlineKeyboardButton(text="🏗️ Ж/б панели", callback_data="insp_mat_2")],
        [InlineKeyboardButton(text="🔲 Блочный", callback_data="insp_mat_3")],
        [InlineKeyboardButton(text="🌲 Дерево", callback_data="insp_mat_4")],
        [InlineKeyboardButton(text="➕ Другой", callback_data="insp_mat_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_inspection_finish_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔨 Черновая (без отделки)", callback_data="insp_fin_1")],
        [InlineKeyboardButton(text="🎨 Предчистовая", callback_data="insp_fin_2")],
        [InlineKeyboardButton(text="✨ Чистовая (с отделкой)", callback_data="insp_fin_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_thermal_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира", callback_data="therm_obj_1")],
        [InlineKeyboardButton(text="🏡 Жилой дом", callback_data="therm_obj_2")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_thermal_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 100 кв.м", callback_data="therm_area_1")],
        [InlineKeyboardButton(text="100-200 кв.м", callback_data="therm_area_2")],
        [InlineKeyboardButton(text="200-300 кв.м", callback_data="therm_area_3")],
        [InlineKeyboardButton(text="свыше 300 кв.м", callback_data="therm_area_4")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_insurance_type_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Новая ипотека", callback_data="insurance_new")],
        [InlineKeyboardButton(text="🔄 Продление договора", callback_data="insurance_renewal")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_insurance_coverage_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Недвижимость (конструктив)", callback_data="coverage_property")],
        [InlineKeyboardButton(text="❤️ Жизнь", callback_data="coverage_life")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_insurance_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира, комната", callback_data="ins_object_1")],
        [InlineKeyboardButton(text="🏡 Жилой дом/садовый дом/таунхаус", callback_data="ins_object_2")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_deals_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📑 Выписки из ЕГРН", callback_data="deals_egrn")],
        [InlineKeyboardButton(text="📊 Анализ сделок за квартал", callback_data="deals_analysis")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_evaluation_purpose_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 Для банка (ипотека)", callback_data="purpose_1.1")],
        [InlineKeyboardButton(text="👨‍👩‍👧 Для органов опеки", callback_data="purpose_1.2")],
        [InlineKeyboardButton(text="⚖️ Для нотариуса", callback_data="purpose_1.3")],
        [InlineKeyboardButton(text="🏛️ Для суда", callback_data="purpose_1.4")],
        [InlineKeyboardButton(text="🤝 Для купли-продажи", callback_data="purpose_1.5")],
        [InlineKeyboardButton(text="📝 Иная цель", callback_data="purpose_1.6")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_banks_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сбербанк", callback_data="bank_Сбербанк"),
         InlineKeyboardButton(text="ВТБ", callback_data="bank_ВТБ")],
        [InlineKeyboardButton(text="Дом.РФ", callback_data="bank_Дом.РФ"),
         InlineKeyboardButton(text="Россельхозбанк", callback_data="bank_Россельхозбанк")],
        [InlineKeyboardButton(text="Альфа-Банк", callback_data="bank_Альфа-Банк"),
         InlineKeyboardButton(text="Совкомбанк", callback_data="bank_Совкомбанк")],
        [InlineKeyboardButton(text="Газпромбанк", callback_data="bank_Газпромбанк"),
         InlineKeyboardButton(text="Промсвязьбанк", callback_data="bank_Промсвязьбанк")],
        [InlineKeyboardButton(text="ПримСоцБанк", callback_data="bank_ПримСоцБанк"),
         InlineKeyboardButton(text="Уралсиб", callback_data="bank_Уралсиб")],
        [InlineKeyboardButton(text="АК Барс Банк", callback_data="bank_АК Барс Банк"),
         InlineKeyboardButton(text="Райффайзенбанк", callback_data="bank_Райффайзенбанк")],
        [InlineKeyboardButton(text="Челябинвестбанк", callback_data="bank_Челябинвестбанк"),
         InlineKeyboardButton(text="УБРиР", callback_data="bank_УБРиР")],
        [InlineKeyboardButton(text="Ипотека24", callback_data="bank_Ипотека24"),
         InlineKeyboardButton(text="Новикомбанк", callback_data="bank_Новикомбанк")],
        [InlineKeyboardButton(text="Евразийский банк", callback_data="bank_Евразийский банк"),
         InlineKeyboardButton(text="Росвоенипотека", callback_data="bank_Росвоенипотека")],
        [InlineKeyboardButton(text="Уралпромбанк", callback_data="bank_Уралпромбанк"),
         InlineKeyboardButton(text="Другой банк", callback_data="bank_Другой")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_mortgage_purpose_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Оформление ипотеки", callback_data="mortgage_1")],
        [InlineKeyboardButton(text="📝 Оформление закладной", callback_data="mortgage_2")],
        [InlineKeyboardButton(text="🔄 Рефинансирование", callback_data="mortgage_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_object_types_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира, комната", callback_data="object_1")],
        [InlineKeyboardButton(text="🌳 Земельный участок", callback_data="object_2")],
        [InlineKeyboardButton(text="🏡 Жилой дом/садовый дом/таунхаус", callback_data="object_3")],
        [InlineKeyboardButton(text="🏢 Нежилое помещение", callback_data="object_4")],
        [InlineKeyboardButton(text="🏭 Нежилое здание", callback_data="object_5")],
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="object_6")],
        [InlineKeyboardButton(text="🅿️ Машиноместо", callback_data="object_7")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_flood_object_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира, комната", callback_data="flood_1")],
        [InlineKeyboardButton(text="🏡 Жилой дом/садовый дом/таунхаус", callback_data="flood_2")],
        [InlineKeyboardButton(text="🏢 Нежилое помещение", callback_data="flood_3")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_report_type_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Краткая справка", callback_data="report_1")],
        [InlineKeyboardButton(text="📊 Отчет об оценке", callback_data="report_2")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_documents_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Прикрепить документы", callback_data="attach_docs")],
        [InlineKeyboardButton(text="✅ Отправить без документов", callback_data="submit_no_docs")]
    ])


def get_main_menu_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


def calculate_mortgage_cost(bank, object_type, mortgage_purpose, distance_km, in_city):
    """
    Расчет стоимости для ипотеки
    in_city: True если объект в Челябинске
    """
    group1 = ['Сбербанк', 'Россельхозбанк', 'Челябинвестбанк', 'Росвоенипотека']
    group2 = ['ВТБ', 'ПримСоцБанк', 'Дом.РФ', 'Альфа-Банк']

    base_price = 0

    if object_type == "Квартира, комната":
        if mortgage_purpose == "Оформление ипотеки":
            base_price = 2500 if bank in group1 else 2900
        elif mortgage_purpose == "Оформление закладной":
            if bank in group2:
                base_price = 4000
            else:
                base_price = 3000
                # Для закладной всегда выезд = 0
                in_city = True
        elif mortgage_purpose == "Рефинансирование":
            base_price = 6900 if bank in group2 else 5900

    elif object_type == "Земельный участок":
        if mortgage_purpose == "Оформление ипотеки":
            base_price = 2500 if bank in group1 else 2900
        elif mortgage_purpose == "Оформление закладной":
            if bank in group2:
                base_price = 4000
            else:
                base_price = 3000
                in_city = True
        elif mortgage_purpose == "Рефинансирование":
            base_price = 6900 if bank in group2 else 5900

    elif object_type == "Жилой дом/садовый дом/таунхаус":
        if mortgage_purpose == "Рефинансирование":
            base_price = 6900 if bank in group2 else 5900
        else:
            base_price = 2500 if bank in group1 else 2900

    elif object_type == "Нежилое помещение":
        base_price = 6000

    elif object_type == "Нежилое здание":
        base_price = 7000

    elif object_type in ["Гараж", "Машиноместо"]:
        base_price = 3500

    # Выезд = 0 если объект в городе
    travel_cost = 0 if in_city else round(distance_km * 35, 2)

    return base_price, travel_cost, base_price + travel_cost


def calculate_other_purpose_cost(object_type, report_type, distance_km, in_city):
    """
    Расчет стоимости для других целей
    in_city: True если объект в Челябинске
    """
    if report_type == "Краткая справка":
        if object_type in ["Квартира, комната", "Гараж", "Машиноместо"]:
            return 1000, 0, 1000
        elif object_type in ["Жилой дом/садовый дом/таунхаус", "Нежилое помещение", "Нежилое здание"]:
            return 1500, 0, 1500
    else:
        base_price = 0
        if object_type == "Квартира, комната":
            base_price = 2500
        elif object_type == "Земельный участок":
            base_price = 3000
        elif object_type == "Жилой дом/садовый дом/таунхаус":
            base_price = 5900
        elif object_type == "Нежилое помещение":
            base_price = 6000
        elif object_type == "Нежилое здание":
            base_price = 7000
        elif object_type in ["Гараж", "Машиноместо"]:
            base_price = 3500

        # Выезд = 0 если объект в городе
        travel_cost = 0 if in_city else round(distance_km * 35, 2)

        return base_price, travel_cost, base_price + travel_cost


def calculate_flood_cost(object_type, rooms_count, distance_km, in_city):
    """
    Расчет стоимости оценки ущерба
    in_city: True если объект в Челябинске
    """
    base_price = 6000 if object_type in ["Квартира, комната", "Жилой дом/садовый дом/таунхаус"] else 7000
    room_multiplier = 1500 if object_type in ["Квартира, комната", "Жилой дом/садовый дом/таунхаус"] else 2000
    rooms_cost = (rooms_count - 1) * room_multiplier if rooms_count > 1 else 0

    # Выезд = 0 если объект в городе
    travel_cost = 0 if in_city else round(distance_km * 35, 2)

    return base_price, rooms_cost, travel_cost, base_price + rooms_cost + travel_cost


def calculate_insurance_cost(object_type, balance):
    if object_type == "Квартира, комната":
        cost = balance * 0.001
    else:
        cost = balance * 0.003
    return round(cost, 2)


def calculate_acceptance_cost(area, distance_km, in_city):
    """
    Расчет стоимости приемки
    in_city: True если объект в Челябинске
    """
    if area == "до 150 кв.м":
        base_price = 15000
    elif area == "150-250 кв.м":
        base_price = 18000
    else:
        base_price = 20000

    # Выезд = 0 если объект в городе
    travel_cost = 0 if in_city else round(distance_km * 35, 2)

    return base_price, travel_cost, base_price + travel_cost


def calculate_inspection_cost(area, distance_km, in_city):
    """
    Расчет стоимости обследования
    in_city: True если объект в Челябинске
    """
    areas = {"до 150 кв.м": 10000, "150-250 кв.м": 12000, "250-350 кв.м": 15000, "свыше 350 кв.м": 18000}
    base_price = areas.get(area, 10000)

    # Выезд = 0 если объект в городе
    travel_cost = 0 if in_city else round(distance_km * 35, 2)

    return base_price, travel_cost, base_price + travel_cost


def calculate_thermal_cost(object_type, area, distance_km, in_city):
    """
    Расчет стоимости тепловизионного обследования
    in_city: True если объект в Челябинске
    """
    if object_type == "Квартира":
        areas = {"до 100 кв.м": 3000, "100-200 кв.м": 3500, "200-300 кв.м": 4000, "свыше 300 кв.м": 4500}
    else:
        areas = {"до 100 кв.м": 5000, "100-200 кв.м": 5500, "200-300 кв.м": 6000, "свыше 300 кв.м": 6500}

    base_price = areas.get(area, 3000)

    # Выезд = 0 если объект в городе
    travel_cost = 0 if in_city else round(distance_km * 35, 2)

    return base_price, travel_cost, base_price + travel_cost


async def format_admin_message(user_data: dict) -> str:
    service = user_data.get('service')

    if service == 'service_1':
        bank = user_data.get('bank')
        mortgage_purpose = user_data.get('mortgage_purpose')
        purpose_name = user_data.get('purpose_name')
        report_type = user_data.get('report_type')

        msg = "💎 <b>Оценка недвижимости</b>\n\n"

        if bank:
            msg += f"Банк: {bank}\n"
            msg += f"Цель: {mortgage_purpose}\n"
        elif purpose_name:
            msg += f"Цель: {purpose_name}\n"
            msg += f"Форма: {report_type}\n"

        msg += f"Объект: {user_data.get('object_type')}\n"
        msg += f"Адрес: {user_data.get('address')}\n"

        if user_data.get('full_address'):
            msg += f"Распознанный адрес: {user_data.get('full_address')}\n"

        msg += f"Расстояние: {user_data.get('distance_km', 0)} км\n"
        msg += f"Дата осмотра: {user_data.get('date')}\n"
        msg += f"Стоимость: {user_data.get('cost')} ₽"

    elif service == 'service_2':
        msg = "💧 <b>Оценка ущерба после затопления</b>\n\n"
        msg += f"Объект: {user_data.get('object_type')}\n"
        msg += f"Пострадало помещений: {user_data.get('rooms_count')}\n"
        msg += f"Адрес: {user_data.get('address')}\n"

        if user_data.get('full_address'):
            msg += f"Распознанный адрес: {user_data.get('full_address')}\n"

        msg += f"Расстояние: {user_data.get('distance_km', 0)} км\n"
        msg += f"Дата осмотра: {user_data.get('date')}\n"
        msg += f"Стоимость: {user_data.get('cost')} ₽"

    elif service == 'service_5':
        msg = "🛡️ <b>Ипотечное страхование</b>\n\n"
        insurance_type = "Новая ипотека" if user_data.get('insurance_type') == 'new' else "Продление договора"
        msg += f"Тип: {insurance_type}\n"
        msg += f"Страхование: {user_data.get('insurance_coverage_name')}\n"
        msg += f"Объект: {user_data.get('insurance_object')}\n"
        msg += f"Остаток по ипотеке: {user_data.get('mortgage_balance')} ₽\n"
        msg += f"Предварительная стоимость: {user_data.get('insurance_cost')} ₽"

    else:
        msg = f"Новая заявка\n\nСервис: {service}"

    return msg


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Form.waiting_for_service)

    welcome_text = (
        "🏢 <b>Добро пожаловать!</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        "Вас приветствует компания <b><i>НЭК Перспектива</i></b>\n\n"
        "💼 Профессиональные услуги:\n"
        "• Оценка недвижимости\n"
        "• БТИ и кадастровые работы\n"
        "• Строительные экспертизы\n"
        "• Ипотечное страхование\n"
        "• Сделки с недвижимостью\n\n"
        "━━━━━━━━━━━━━━\n"
        "👇 Выберите услугу:"
    )

    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def cmd_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.waiting_for_service)

    welcome_text = (
        "🏢 <b>Главное меню</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        "👇 Выберите услугу:"
    )

    await callback.message.edit_text(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "back")
async def process_back(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()

    # Навигация назад в зависимости от текущего состояния
    if current_state == Form.waiting_for_bti_service:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_bti_object_type:
        await state.set_state(Form.waiting_for_bti_service)
        await callback.message.edit_text(
            "📋 <b>БТИ / Кадастр / Межевание</b>\n\nВыберите услугу:",
            reply_markup=get_bti_services_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_bti_surveying_service:
        await state.set_state(Form.waiting_for_bti_service)
        await callback.message.edit_text(
            "📋 <b>БТИ / Кадастр / Межевание</b>\n\nВыберите услугу:",
            reply_markup=get_bti_services_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_bti_acts_service:
        await state.set_state(Form.waiting_for_bti_service)
        await callback.message.edit_text(
            "📋 <b>БТИ / Кадастр / Межевание</b>\n\nВыберите услугу:",
            reply_markup=get_bti_services_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_expertise_type:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_expertise_stage:
        await state.set_state(Form.waiting_for_expertise_type)
        await callback.message.edit_text(
            "🔨 <b>Строительно-техническая экспертиза / Обследования</b>\n\nВыберите тип:",
            reply_markup=get_expertise_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_insurance_type:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_insurance_coverage:
        await state.set_state(Form.waiting_for_insurance_type)
        await callback.message.edit_text(
            "🛡️ <b>Ипотечное страхование</b>\n\nВыберите тип:",
            reply_markup=get_insurance_type_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_insurance_object:
        await state.set_state(Form.waiting_for_insurance_coverage)
        await callback.message.edit_text(
            "🛡️ <b>Что страхуем?</b>",
            reply_markup=get_insurance_coverage_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_deals_service:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_purpose:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_bank:
        await state.set_state(Form.waiting_for_purpose)
        await callback.message.edit_text(
            "💎 <b>Оценка недвижимости</b>\n\nВыберите цель:",
            reply_markup=get_evaluation_purpose_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_mortgage_purpose:
        await state.set_state(Form.waiting_for_bank)
        await callback.message.edit_text(
            "🏦 <b>Оценка для банка</b>\n\nВыберите банк:",
            reply_markup=get_banks_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_report_type:
        await state.set_state(Form.waiting_for_purpose)
        await callback.message.edit_text(
            "💎 <b>Оценка недвижимости</b>\n\nВыберите цель:",
            reply_markup=get_evaluation_purpose_menu(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_object_type:
        service = user_data.get('service')
        if service == 'service_1' and user_data.get('bank'):
            await state.set_state(Form.waiting_for_mortgage_purpose)
            await callback.message.edit_text(
                f"🏦 Банк: {user_data.get('bank')}\n\nВыберите цель:",
                reply_markup=get_mortgage_purpose_menu(),
                parse_mode="HTML"
            )
        elif service == 'service_1' and user_data.get('report_type'):
            await state.set_state(Form.waiting_for_report_type)
            await callback.message.edit_text(
                f"📊 {user_data.get('purpose_name')}\n\nФорма оценки:",
                reply_markup=get_report_type_menu(),
                parse_mode="HTML"
            )
        elif service == 'service_2':
            await state.set_state(Form.waiting_for_service)
            await callback.message.edit_text(
                "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
                reply_markup=get_main_menu(),
                parse_mode="HTML"
            )
        else:
            await state.set_state(Form.waiting_for_purpose)
            await callback.message.edit_text(
                "💎 <b>Оценка недвижимости</b>\n\nВыберите цель:",
                reply_markup=get_evaluation_purpose_menu(),
                parse_mode="HTML"
            )
    elif current_state == Form.waiting_for_flood_rooms:
        await state.set_state(Form.waiting_for_object_type)
        await callback.message.edit_text(
            "🏠 <b>Какой объект пострадал?</b>",
            reply_markup=get_flood_object_types(),
            parse_mode="HTML"
        )
    elif current_state == Form.waiting_for_address:
        service = user_data.get('service')
        bti_service = user_data.get('bti_service')

        if service == 'service_2':
            await state.set_state(Form.waiting_for_flood_rooms)
            await callback.message.edit_text(
                "🔢 <b>Количество пострадавших помещений</b>\n\nВведите число:",
                reply_markup=get_back_button(),
                parse_mode="HTML"
            )
        elif bti_service in ["2", "5"]:
            await state.set_state(Form.waiting_for_bti_object_type)
            await callback.message.edit_text(
                "🏠 <b>Выберите тип объекта:</b>",
                reply_markup=get_bti_object_types_menu(),
                parse_mode="HTML"
            )
        elif bti_service:
            await state.set_state(Form.waiting_for_bti_service)
            await callback.message.edit_text(
                "📋 <b>БТИ / Кадастр / Межевание</b>\n\nВыберите услугу:",
                reply_markup=get_bti_services_menu(),
                parse_mode="HTML"
            )
        else:
            await state.set_state(Form.waiting_for_object_type)
            await callback.message.edit_text(
                "🏠 <b>Выберите тип объекта:</b>",
                reply_markup=get_object_types_menu(),
                parse_mode="HTML"
            )
    else:
        await state.set_state(Form.waiting_for_service)
        await callback.message.edit_text(
            "🏢 <b>Главное меню</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("service_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data
    await state.update_data(service=service_id)

    if service_id == "service_1":
        await state.set_state(Form.waiting_for_purpose)
        text = "💎 <b>Оценка недвижимости</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите цель:"
        await callback.message.edit_text(text, reply_markup=get_evaluation_purpose_menu(), parse_mode="HTML")

    elif service_id == "service_2":
        await state.set_state(Form.waiting_for_object_type)
        text = "💧 <b>Оценка ущерба после затопления</b>\n━━━━━━━━━━━━━━\n\n🏠 Какой объект пострадал?"
        await callback.message.edit_text(text, reply_markup=get_flood_object_types(), parse_mode="HTML")

    elif service_id == "service_3":
        await state.set_state(Form.waiting_for_bti_service)
        text = "📋 <b>БТИ / Кадастр / Межевание</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:"
        await callback.message.edit_text(text, reply_markup=get_bti_services_menu(), parse_mode="HTML")

    elif service_id == "service_4":
        await state.set_state(Form.waiting_for_expertise_type)
        text = "🔨 <b>Строительно-техническая экспертиза / Обследования</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите тип:"
        await callback.message.edit_text(text, reply_markup=get_expertise_menu(), parse_mode="HTML")

    elif service_id == "service_5":
        await state.set_state(Form.waiting_for_insurance_type)
        text = "🛡️ <b>Ипотечное страхование</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите тип:"
        await callback.message.edit_text(text, reply_markup=get_insurance_type_menu(), parse_mode="HTML")

    elif service_id == "service_6":
        await state.set_state(Form.waiting_for_deals_service)
        text = "🏢 <b>Сделки с недвижимостью</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:"
        await callback.message.edit_text(text, reply_markup=get_deals_menu(), parse_mode="HTML")

    await callback.answer()


# БТИ HANDLERS
@dp.callback_query(F.data.startswith("bti_"))
async def process_bti_service(callback: CallbackQuery, state: FSMContext):
    bti_id = callback.data.split("_")[1]
    bti_services = {
        "1": "Выписка из технического паспорта",
        "2": "Технический паспорт",
        "3": "Технический план",
        "4": "Межевание (земля)",
        "5": "Акты, справки"
    }
    bti_service_name = bti_services.get(bti_id)
    await state.update_data(bti_service=bti_id, bti_service_name=bti_service_name)

    if bti_id == "1":
        await state.set_state(Form.waiting_for_address)
        text = (
            f"📄 <b>{bti_service_name}</b>\n━━━━━━━━━━━━━━\n\n"
            "📍 Введите адрес:\n"
            "Город, улица, дом, кв\n"
            "или\nКадастровый номер"
        )
        await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")

    elif bti_id in ["2", "5"]:
        if bti_id == "2":
            await state.set_state(Form.waiting_for_bti_object_type)
            text = f"📋 <b>{bti_service_name}</b>\n━━━━━━━━━━━━━━\n\n"

            try:
                photo_path = PRICE_PHOTOS['tech_passport']
                if os.path.exists(photo_path):
                    await callback.message.delete()
                    photo = FSInputFile(photo_path)
                    text += "💰 Прайс-лист\n\n👇 Выберите объект:"
                    sent = await callback.message.answer_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=get_tech_passport_options(),
                        parse_mode="HTML"
                    )
                    await callback.answer()
                    return
            except:
                pass

            text += "👇 Выберите объект:"
            await callback.message.edit_text(text, reply_markup=get_tech_passport_options(), parse_mode="HTML")
        else:
            await state.set_state(Form.waiting_for_bti_object_type)
            text = f"📑 <b>{bti_service_name}</b>\n━━━━━━━━━━━━━━\n\n"

            try:
                photo_path = PRICE_PHOTOS['acts']
                if os.path.exists(photo_path):
                    await callback.message.delete()
                    photo = FSInputFile(photo_path)
                    text += "💰 Прайс-лист\n\n👇 Выберите услугу:"
                    await callback.message.answer_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=get_acts_options(),
                        parse_mode="HTML"
                    )
                    await callback.answer()
                    return
            except:
                pass

            text += "👇 Выберите услугу:"
            await callback.message.edit_text(text, reply_markup=get_acts_options(), parse_mode="HTML")

    elif bti_id == "3":
        text = "📐 <b>Технический план</b>\n━━━━━━━━━━━━━━\n\n"

        try:
            photo_path = PRICE_PHOTOS['tech_plan']
            if os.path.exists(photo_path):
                await callback.message.delete()
                photo = FSInputFile(photo_path)
                text += "💰 Прайс-лист\n\n👇 Выберите действие:"
                await callback.message.answer_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=get_tech_plan_options(),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        except:
            pass

        text += "👇 Выберите действие:"
        await callback.message.edit_text(text, reply_markup=get_tech_plan_options(), parse_mode="HTML")

    elif bti_id == "4":
        text = "🗺️ <b>Межевание (земля)</b>\n━━━━━━━━━━━━━━\n\n"

        try:
            photo_path = PRICE_PHOTOS['surveying']
            if os.path.exists(photo_path):
                await callback.message.delete()
                photo = FSInputFile(photo_path)
                text += "💰 Прайс-лист\n\n👇 Выберите действие:"
                await callback.message.answer_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=get_surveying_options(),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        except:
            pass

        text += "👇 Выберите действие:"
        await callback.message.edit_text(text, reply_markup=get_surveying_options(), parse_mode="HTML")

    await callback.answer()


@dp.callback_query(F.data == "tech_plan_price")
async def process_tech_plan_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_object_type)
    text = "📐 <b>Технический план</b>\n━━━━━━━━━━━━━━\n\n🏠 Выберите объект:"
    await callback.message.edit_text(text, reply_markup=get_tech_plan_objects(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("tech_plan_obj_"))
async def process_tech_plan_object(callback: CallbackQuery, state: FSMContext):
    obj_id = callback.data.split("_")[3]
    objects = {
        "1": "Квартира, комната",
        "2": "Жилой дом/садовый дом/таунхаус",
        "3": "Нежилое помещение",
        "4": "Нежилое здание",
        "5": "Гараж",
        "6": "Раздел дома",
        "7": "Раздел/объединение помещений"
    }
    obj_type = objects.get(obj_id)
    await state.update_data(tech_plan_object=obj_type, is_tech_plan=True)
    await state.set_state(Form.waiting_for_address)

    text = f"📐 <b>Технический план</b>\n🏠 {obj_type}\n━━━━━━━━━━━━━━\n\n📍 Введите адрес или кадастровый номер:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "surveying_price")
async def process_surveying_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_surveying_service)
    text = "🗺️ <b>Межевание (земля)</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:"
    await callback.message.edit_text(text, reply_markup=get_surveying_services(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("surv_serv_"))
async def process_surveying_service(callback: CallbackQuery, state: FSMContext):
    serv_id = callback.data.split("_")[2]
    services = {
        "1": "Уточнение границ зем. участка",
        "2": "Раздел/объединение участка",
        "3": "Схема для КУиЗО",
        "4": "Перераспределение (межевой)",
        "5": "Перераспределение (схема + межевой)",
        "6": "Схема под гараж",
        "7": "Межевой по распоряжению",
        "8": "Межевой для суда",
        "9": "Межевой на сервитут",
        "other": "Другое"
    }
    service_name = services.get(serv_id, "Другое")
    await state.update_data(surveying_service=service_name)
    await state.set_state(Form.waiting_for_address)

    text = f"🗺️ <b>Межевание</b>\n📋 {service_name}\n━━━━━━━━━━━━━━\n\n📍 Введите кадастровый номер:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "acts_price")
async def process_acts_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_acts_service)
    text = "📑 <b>Акты, справки</b>\n━━━━━━━━━━━━━━\n\n👇 Выберите услугу:"
    await callback.message.edit_text(text, reply_markup=get_acts_services(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("acts_serv_"))
async def process_acts_service(callback: CallbackQuery, state: FSMContext):
    serv_id = callback.data.split("_")[2]
    services = {
        "1": "Документы на акт ввода до 1500 кв.м",
        "2": "На гараж",
        "3": "Акт сноса",
        "4": "Справка о местоположении (комната)",
        "5": "Справка о стоимости",
        "6": "Заполнение уведомлений",
        "other": "Другое"
    }
    service_name = services.get(serv_id, "Другое")
    await state.update_data(acts_service=service_name)

    # Отправка администраторам
    admin_text = f"📑 <b>Акты, справки</b>\n\nУслуга: {service_name}"
    await send_to_admins(admin_text, get_user_info(callback.from_user))

    text = (
        f"📑 <b>Акты, справки</b>\n{service_name}\n━━━━━━━━━━━━━━\n\n"
        "✅ <b>Заявка принята!</b>\n\n"
        "📞 Специалист свяжется с вами в ближайшее время"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "tech_passport_price")
async def process_tech_passport_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_object_type)
    text = "📋 <b>Технический паспорт</b>\n━━━━━━━━━━━━━━\n\n🏠 Выберите объект:"
    await callback.message.edit_text(text, reply_markup=get_bti_object_types_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("bti_object_"))
async def process_bti_object_type(callback: CallbackQuery, state: FSMContext):
    object_type = callback.data.split("_")[2]
    object_names = {
        "flat": "Квартира",
        "house": "Жилой дом",
        "nonres": "Нежилое помещение",
        "garage": "Гараж"
    }
    object_name = object_names.get(object_type)
    await state.update_data(bti_object_type=object_type, bti_object_name=object_name)
    await state.set_state(Form.waiting_for_address)

    text = f"📋 <b>Технический паспорт</b>\n🏠 {object_name}\n━━━━━━━━━━━━━━\n\n📍 Введите адрес:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


# EXPERTISE HANDLERS
@dp.callback_query(F.data.startswith("expertise_"))
async def process_expertise(callback: CallbackQuery, state: FSMContext):
    exp_id = callback.data.split("_")[1]

    if exp_id == "1":
        await state.update_data(expertise_type="Строительно-техническая экспертиза")
        await state.set_state(Form.waiting_for_expertise_stage)
        text = (
            "🔍 <b>Строительно-техническая экспертиза</b>\n━━━━━━━━━━━━━━\n\n"
            "Я помогу оформить заявку на строительно-техническую экспертизу.\n\n"
            "На каком этапе сейчас находится ваш спор?"
        )
        await callback.message.edit_text(text, reply_markup=get_expertise_stage_menu(), parse_mode="HTML")

    elif exp_id == "2":
        await state.update_data(expertise_type="Приемка жилого дома от застройщика")
        await state.set_state(Form.waiting_for_acceptance_state)
        text = (
            "🏡 <b>Приемка жилого дома от застройщика</b>\n━━━━━━━━━━━━━━\n\n"
            "Я помогу оформить заявку на приёмку жилого дома.\n\n"
            "Состояние внутренней отделки:"
        )
        await callback.message.edit_text(text, reply_markup=get_acceptance_state_menu(), parse_mode="HTML")

    elif exp_id == "3":
        await state.update_data(expertise_type="Техническое обследование перед покупкой")
        await state.set_state(Form.waiting_for_inspection_area)
        text = (
            "🏠 <b>Техническое обследование перед покупкой</b>\n━━━━━━━━━━━━━━\n\n"
            "✔️ Инструментальное обследование\n"
            "✔️ Выявление скрытых дефектов\n"
            "✔️ Оценка состояния дома\n"
            "✔️ Консультация и рекомендации\n\n"
            "Укажите площадь дома:"
        )
        await callback.message.edit_text(text, reply_markup=get_inspection_area_menu(), parse_mode="HTML")

    elif exp_id == "4":
        await state.update_data(expertise_type="Тепловизионное обследование")
        await state.set_state(Form.waiting_for_thermal_object)
        text = (
            "🌡️ <b>Тепловизионное обследование</b>\n━━━━━━━━━━━━━━\n\n"
            "Выберите объект:"
        )
        await callback.message.edit_text(text, reply_markup=get_thermal_object_menu(), parse_mode="HTML")

    await callback.answer()


@dp.callback_query(F.data.startswith("exp_stage_"))
async def process_expertise_stage(callback: CallbackQuery, state: FSMContext):
    stage_id = callback.data.split("_")[2]
    stages = {
        "1": "Идёт судебный процесс",
        "2": "Досудебное урегулирование",
        "3": "Затрудняюсь ответить"
    }
    await state.update_data(expertise_stage=stages.get(stage_id))
    await state.set_state(Form.waiting_for_expertise_object)

    text = "🏠 Какой объект требуется обследовать?"
    await callback.message.edit_text(text, reply_markup=get_expertise_object_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("exp_obj_"))
async def process_expertise_object(callback: CallbackQuery, state: FSMContext):
    obj_id = callback.data.split("_")[2]
    objects = {
        "1": "Квартира",
        "2": "Жилой дом / коттедж",
        "3": "Коммерческий объект",
        "4": "Кровля",
        "5": "Фундамент"
    }
    await state.update_data(expertise_object=objects.get(obj_id, "Другое"))
    await state.set_state(Form.waiting_for_expertise_status)

    text = "🏗️ Объект построен или в процессе?"
    await callback.message.edit_text(text, reply_markup=get_expertise_status_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("exp_status_"))
async def process_expertise_status(callback: CallbackQuery, state: FSMContext):
    status_id = callback.data.split("_")[2]
    statuses = {
        "1": "Построен",
        "2": "В процессе строительства",
        "3": "После ремонта / реконструкции"
    }
    await state.update_data(expertise_status=statuses.get(status_id))
    await state.set_state(Form.waiting_for_expertise_description)

    text = (
        "📝 Опишите коротко проблемы или что вызывает сомнения\n\n"
        "(трещины, протечки, неровная кладка и т.д.)"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.message(Form.waiting_for_expertise_description)
async def process_expertise_description(message: Message, state: FSMContext):
    await state.update_data(expertise_description=message.text)
    await state.set_state(Form.waiting_for_expertise_photos)

    text = (
        "📸 Прикрепите фото проблемных мест\n"
        "(это поможет эксперту предварительно оценить ситуацию)\n\n"
        "или нажмите /done для завершения"
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Form.waiting_for_expertise_photos, F.photo)
async def process_expertise_photos(message: Message, state: FSMContext):
    await message.answer("✅ Фото получено")


@dp.message(Command("done"), Form.waiting_for_expertise_photos)
async def finish_expertise(message: Message, state: FSMContext):
    user_data = await state.get_data()

    admin_text = (
        f"🔍 <b>{user_data.get('expertise_type')}</b>\n\n"
        f"Этап: {user_data.get('expertise_stage')}\n"
        f"Объект: {user_data.get('expertise_object')}\n"
        f"Статус: {user_data.get('expertise_status')}\n"
        f"Описание: {user_data.get('expertise_description')}"
    )
    await send_to_admins(admin_text, get_user_info(message.from_user))

    text = "✅ <b>Заявка принята!</b>\n\n📞 Специалист свяжется с вами в ближайшее время"
    await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
    await state.clear()


# ACCEPTANCE HANDLERS
@dp.callback_query(F.data.startswith("acc_state_"))
async def process_acceptance_state(callback: CallbackQuery, state: FSMContext):
    state_id = callback.data.split("_")[2]
    states = {
        "1": "Черновая",
        "2": "Предчистовая",
        "3": "Чистовая"
    }
    await state.update_data(acceptance_state=states.get(state_id))
    await state.set_state(Form.waiting_for_acceptance_material)

    text = "🧱 Материал стен?"
    await callback.message.edit_text(text, reply_markup=get_acceptance_material_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("acc_mat_"))
async def process_acceptance_material(callback: CallbackQuery, state: FSMContext):
    mat_id = callback.data.split("_")[2]
    materials = {
        "1": "Кирпич",
        "2": "Ж/б панели",
        "3": "Блочный",
        "4": "Дерево",
        "other": "Другой"
    }
    await state.update_data(acceptance_material=materials.get(mat_id, "Другой"))
    await state.set_state(Form.waiting_for_acceptance_area)

    text = "📏 Площадь объекта?"
    await callback.message.edit_text(text, reply_markup=get_acceptance_area_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("acc_area_"))
async def process_acceptance_area(callback: CallbackQuery, state: FSMContext):
    area_id = callback.data.split("_")[2]
    areas = {
        "1": "до 150 кв.м",
        "2": "150-250 кв.м",
        "3": "250-500 кв.м"
    }
    area = areas.get(area_id)
    await state.update_data(acceptance_area=area)
    await state.set_state(Form.waiting_for_address)

    text = "📍 Введите адрес объекта:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


# INSPECTION HANDLERS
@dp.callback_query(F.data.startswith("insp_area_"))
async def process_inspection_area(callback: CallbackQuery, state: FSMContext):
    area_id = callback.data.split("_")[2]
    areas = {
        "1": "до 150 кв.м",
        "2": "150-250 кв.м",
        "3": "250-350 кв.м",
        "4": "свыше 350 кв.м"
    }
    area = areas.get(area_id)
    await state.update_data(inspection_area=area)
    await state.set_state(Form.waiting_for_inspection_material)

    text = "🧱 Материал стен дома?"
    await callback.message.edit_text(text, reply_markup=get_inspection_material_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("insp_mat_"))
async def process_inspection_material(callback: CallbackQuery, state: FSMContext):
    mat_id = callback.data.split("_")[2]
    materials = {
        "1": "Кирпич",
        "2": "Ж/б панели",
        "3": "Блочный",
        "4": "Дерево",
        "other": "Другой"
    }
    await state.update_data(inspection_material=materials.get(mat_id, "Другой"))
    await state.set_state(Form.waiting_for_inspection_finish)

    text = "🎨 Состояние внутренней отделки?"
    await callback.message.edit_text(text, reply_markup=get_inspection_finish_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("insp_fin_"))
async def process_inspection_finish(callback: CallbackQuery, state: FSMContext):
    fin_id = callback.data.split("_")[2]
    finishes = {
        "1": "Черновая",
        "2": "Предчистовая",
        "3": "Чистовая"
    }
    await state.update_data(inspection_finish=finishes.get(fin_id))
    await state.set_state(Form.waiting_for_address)

    text = "📍 Введите адрес объекта:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


# THERMAL HANDLERS
@dp.callback_query(F.data.startswith("therm_obj_"))
async def process_thermal_object(callback: CallbackQuery, state: FSMContext):
    obj_id = callback.data.split("_")[2]
    objects = {
        "1": "Квартира",
        "2": "Жилой дом"
    }
    await state.update_data(thermal_object=objects.get(obj_id))
    await state.set_state(Form.waiting_for_thermal_area)

    text = "📏 Площадь объекта?"
    await callback.message.edit_text(text, reply_markup=get_thermal_area_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("therm_area_"))
async def process_thermal_area(callback: CallbackQuery, state: FSMContext):
    area_id = callback.data.split("_")[2]
    areas = {
        "1": "до 100 кв.м",
        "2": "100-200 кв.м",
        "3": "200-300 кв.м",
        "4": "свыше 300 кв.м"
    }
    area = areas.get(area_id)
    await state.update_data(thermal_area=area)
    await state.set_state(Form.waiting_for_address)

    text = "📍 Введите адрес объекта:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


# EVALUATION HANDLERS
@dp.callback_query(F.data.startswith("purpose_"))
async def process_evaluation_purpose(callback: CallbackQuery, state: FSMContext):
    purpose_id = callback.data.split("_")[1]

    if purpose_id == "1.1":
        await state.set_state(Form.waiting_for_bank)
        await callback.message.edit_text(
            "🏦 <b>Оценка для банка</b>\n━━━━━━━━━━━━━━\n\nВыберите банк:",
            reply_markup=get_banks_menu(),
            parse_mode="HTML"
        )
    else:
        purpose_names = {
            "1.2": "Для органов опеки",
            "1.3": "Для нотариуса",
            "1.4": "Для суда",
            "1.5": "Для купли-продажи",
            "1.6": "Иная цель"
        }
        purpose_name = purpose_names.get(purpose_id)
        await state.update_data(purpose=purpose_id, purpose_name=purpose_name)
        await state.set_state(Form.waiting_for_report_type)
        await callback.message.edit_text(
            f"📊 <b>{purpose_name}</b>\n━━━━━━━━━━━━━━\n\nФорма оценки:",
            reply_markup=get_report_type_menu(),
            parse_mode="HTML"
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("bank_"))
async def process_bank(callback: CallbackQuery, state: FSMContext):
    bank_name = callback.data.split("_", 1)[1]
    await state.update_data(bank=bank_name)
    await state.set_state(Form.waiting_for_mortgage_purpose)
    text = f"🏦 Банк: {bank_name}\n━━━━━━━━━━━━━━\n\n👇 Выберите цель:"
    await callback.message.edit_text(text, reply_markup=get_mortgage_purpose_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("mortgage_"))
async def process_mortgage_purpose(callback: CallbackQuery, state: FSMContext):
    purpose_id = callback.data.split("_")[1]
    purpose_names = {
        "1": "Оформление ипотеки",
        "2": "Оформление закладной",
        "3": "Рефинансирование"
    }
    mortgage_purpose = purpose_names.get(purpose_id)
    await state.update_data(mortgage_purpose=mortgage_purpose)
    await state.set_state(Form.waiting_for_object_type)
    text = f"🎯 Цель: {mortgage_purpose}\n━━━━━━━━━━━━━━\n\n🏠 Выберите объект:"
    await callback.message.edit_text(text, reply_markup=get_object_types_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("report_"))
async def process_report_type(callback: CallbackQuery, state: FSMContext):
    report_id = callback.data.split("_")[1]
    report_type = "Краткая справка" if report_id == "1" else "Отчет об оценке"
    await state.update_data(report_type=report_type)
    await state.set_state(Form.waiting_for_object_type)
    text = f"📝 Форма: {report_type}\n━━━━━━━━━━━━━━\n\n🏠 Выберите объект:"
    await callback.message.edit_text(text, reply_markup=get_object_types_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("object_"))
async def process_object_type(callback: CallbackQuery, state: FSMContext):
    object_id = callback.data.split("_")[1]
    object_names = {
        "1": "Квартира, комната",
        "2": "Земельный участок",
        "3": "Жилой дом/садовый дом/таунхаус",
        "4": "Нежилое помещение",
        "5": "Нежилое здание",
        "6": "Гараж",
        "7": "Машиноместо"
    }
    object_type = object_names.get(object_id)
    await state.update_data(object_type=object_type)
    await state.set_state(Form.waiting_for_address)

    text = f"🏠 Объект: {object_type}\n━━━━━━━━━━━━━━\n\n📍 Введите адрес:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("flood_"))
async def process_flood_object_type(callback: CallbackQuery, state: FSMContext):
    flood_id = callback.data.split("_")[1]
    flood_types = {
        "1": "Квартира, комната",
        "2": "Жилой дом/садовый дом/таунхаус",
        "3": "Нежилое помещение"
    }
    object_type = flood_types.get(flood_id)
    await state.update_data(object_type=object_type)
    await state.set_state(Form.waiting_for_flood_rooms)
    text = f"🏠 Объект: {object_type}\n━━━━━━━━━━━━━━\n\n🔢 Количество пострадавших помещений:"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.message(Form.waiting_for_flood_rooms)
async def process_flood_rooms(message: Message, state: FSMContext):
    try:
        rooms_count = int(message.text.strip())
        if rooms_count < 1:
            await message.answer("❌ Введите положительное число")
            return
        await state.update_data(rooms_count=rooms_count)
        await state.set_state(Form.waiting_for_address)
        text = "📍 Введите адрес объекта:"
        await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Введите корректное число")


# ADDRESS PROCESSING
@dp.message(Form.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    address = message.text.strip()
    await state.update_data(address=address)

    user_data = await state.get_data()
    service = user_data.get('service')
    bti_service = user_data.get('bti_service')

    # БТИ выписка
    if bti_service == "1":
        admin_text = f"📄 <b>Выписка из технического паспорта</b>\n\nАдрес: {address}\nСтоимость: 500 ₽"
        await send_to_admins(admin_text, get_user_info(message.from_user))

        text = (
            "📄 <b>Выписка из техпаспорта</b>\n━━━━━━━━━━━━━━\n\n"
            "✅ <b>Заявка принята!</b>\n\n"
            "💎 Стоимость: 500 ₽\n"
            "⏱️ Готовность: в течение дня\n\n"
            "📞 Специалист свяжется с вами"
        )
        await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
        return

    # БТИ техпаспорт
    if bti_service == "2":
        admin_text = (
            f"📋 <b>Технический паспорт</b>\n\n"
            f"Тип: {user_data.get('bti_object_name')}\n"
            f"Адрес: {address}"
        )
        await send_to_admins(admin_text, get_user_info(message.from_user))

        text = (
            "📋 <b>Технический паспорт</b>\n━━━━━━━━━━━━━━\n\n"
            "✅ <b>Заявка принята!</b>\n\n"
            "📞 Специалист свяжется с вами"
        )
        await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
        return

    # БТИ межевание или акты
    if user_data.get('surveying_service'):
        admin_text = f"🗺️ <b>Межевание</b>\n\nУслуга: {user_data.get('surveying_service')}\nАдрес: {address}"
        await send_to_admins(admin_text, get_user_info(message.from_user))

        text = "🗺️ <b>Межевание</b>\n━━━━━━━━━━━━━━\n\n✅ <b>Заявка принята!</b>\n\n📞 Специалист свяжется с вами"
        await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
        return

    # Техплан - отправить без расчета
    if user_data.get('is_tech_plan'):
        admin_text = (
            f"📐 <b>Технический план</b>\n\n"
            f"Объект: {user_data.get('tech_plan_object')}\n"
            f"Адрес: {address}"
        )
        await send_to_admins(admin_text, get_user_info(message.from_user))

        text = "📐 <b>Технический план</b>\n━━━━━━━━━━━━━━\n\n✅ <b>Заявка принята!</b>\n\n📞 Специалист свяжется с вами"
        await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
        return

    # Geocoding для остальных случаев
    processing_msg = await message.answer("🔍 Определяем местоположение...")

    lat, lon, full_address = await geocode_address(address)

    if lat is not None and lon is not None:
        distance_km = calculate_distance(CHELYABINSK_CENTER[0], CHELYABINSK_CENTER[1], lat, lon)
        distance_km = round(distance_km, 1)
        in_city = is_in_chelyabinsk(full_address)
        await state.update_data(distance_km=distance_km, lat=lat, lon=lon, full_address=full_address, in_city=in_city)
    else:
        distance_km = 0
        in_city = True
        await state.update_data(distance_km=0, in_city=True)

    await processing_msg.delete()

    # ОЦЕНКА НЕДВИЖИМОСТИ
    if service == 'service_1':
        bank = user_data.get('bank')
        mortgage_purpose = user_data.get('mortgage_purpose')
        report_type = user_data.get('report_type')
        object_type = user_data.get('object_type')

        if bank and mortgage_purpose:
            base_price, travel_cost, total_cost = calculate_mortgage_cost(
                bank, object_type, mortgage_purpose, distance_km, in_city
            )

            cost_text = "💰 <b>Расчет стоимости</b>\n━━━━━━━━━━━━━━\n\n"

            if lat is not None:
                cost_text += f"📌 Распознан: {full_address}\n\n"

            cost_text += f"📍 Адрес: {address}\n"
            cost_text += f"📏 Расстояние: {distance_km} км\n\n"

            if travel_cost > 0:
                cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
                cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n\n"
                cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"
            else:
                cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"

            cost_text += "📅 Срок: 1-2 дня\n\n"
            cost_text += "⚠️ Дополнительно:\n"
            cost_text += "• >150 кв.м: +1000 ₽/150 кв.м\n"
            cost_text += "• Срочность: ×1.3\n\n"
            cost_text += "📅 Введите дату и время осмотра:"

            await state.update_data(cost=int(total_cost))
            await state.set_state(Form.waiting_for_date)
            await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")

        elif report_type:
            if report_type == "Краткая справка":
                base_price, travel_cost, total_cost = calculate_other_purpose_cost(
                    object_type, report_type, distance_km, in_city
                )
                text = (
                    f"📄 <b>Краткая справка</b>\n━━━━━━━━━━━━━━\n\n"
                    f"💎 Стоимость: {int(total_cost)} ₽\n"
                    f"⏱️ Готовность: в течение дня\n\n"
                    f"📎 Прикрепите документы или отправьте на:\n"
                    f"📧 7511327@mail.ru\n\n"
                    f"📋 Документы:\n"
                    f"1. Выписка ЕГРН\n"
                    f"2. Паспорт заказчика"
                )
                await message.answer(text, reply_markup=get_documents_menu(), parse_mode="HTML")
                await state.update_data(cost=int(total_cost))
                await state.set_state(Form.waiting_for_documents)
            else:
                base_price, travel_cost, total_cost = calculate_other_purpose_cost(
                    object_type, report_type, distance_km, in_city
                )

                cost_text = "📊 <b>Отчет об оценке</b>\n━━━━━━━━━━━━━━\n\n"

                if lat is not None:
                    cost_text += f"📌 Распознан: {full_address}\n\n"

                cost_text += f"📍 Адрес: {address}\n"
                cost_text += f"📏 Расстояние: {distance_km} км\n\n"

                if travel_cost > 0:
                    cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
                    cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n\n"
                    cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"
                else:
                    cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"

                cost_text += "📅 Срок: 1-2 дня\n\n"
                cost_text += "⚠️ Дополнительно:\n"
                cost_text += "• >150 кв.м: +1000 ₽/150 кв.м\n"
                cost_text += "• Срочность: ×1.3\n\n"
                cost_text += "📅 Введите дату и время:"

                await state.update_data(cost=int(total_cost))
                await state.set_state(Form.waiting_for_date)
                await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")

    # ОЦЕНКА УЩЕРБА
    elif service == 'service_2':
        object_type = user_data.get('object_type')
        rooms_count = user_data.get('rooms_count', 1)

        base_price, rooms_cost, travel_cost, total_cost = calculate_flood_cost(
            object_type, rooms_count, distance_km, in_city
        )

        cost_text = "💧 <b>Оценка ущерба</b>\n━━━━━━━━━━━━━━\n\n"

        if lat is not None:
            cost_text += f"📌 Распознан: {full_address}\n\n"

        cost_text += f"📍 Адрес: {address}\n"
        cost_text += f"📏 Расстояние: {distance_km} км\n"
        cost_text += f"🔢 Помещений: {rooms_count}\n\n"

        cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
        if rooms_cost > 0:
            cost_text += f"➕ Доп. помещения: {int(rooms_cost)} ₽\n"
        if travel_cost > 0:
            cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n"
        cost_text += f"\n💎 ИТОГО: {int(total_cost)} ₽\n\n"

        cost_text += "📅 Срок: 3-5 дней\n\n"
        cost_text += "📅 Введите дату осмотра:"

        await state.update_data(cost=int(total_cost))
        await state.set_state(Form.waiting_for_date)
        await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")

    # ПРИЕМКА
    elif user_data.get('acceptance_area'):
        area = user_data.get('acceptance_area')
        base_price, travel_cost, total_cost = calculate_acceptance_cost(area, distance_km, in_city)

        cost_text = "🏡 <b>Приемка дома</b>\n━━━━━━━━━━━━━━\n\n"

        if lat is not None:
            cost_text += f"📌 Распознан: {full_address}\n\n"

        cost_text += f"📍 Адрес: {address}\n"
        cost_text += f"📏 Расстояние: {distance_km} км\n\n"

        if travel_cost > 0:
            cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
            cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n\n"
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"
        else:
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"

        cost_text += "📅 Введите дату выезда:"

        await state.update_data(cost=int(total_cost))
        await state.set_state(Form.waiting_for_date)
        await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")

    # ОБСЛЕДОВАНИЕ
    elif user_data.get('inspection_area'):
        area = user_data.get('inspection_area')
        base_price, travel_cost, total_cost = calculate_inspection_cost(area, distance_km, in_city)

        cost_text = "🏠 <b>Обследование дома</b>\n━━━━━━━━━━━━━━\n\n"

        if lat is not None:
            cost_text += f"📌 Распознан: {full_address}\n\n"

        cost_text += f"📍 Адрес: {address}\n"
        cost_text += f"📏 Расстояние: {distance_km} км\n\n"

        if travel_cost > 0:
            cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
            cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n\n"
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"
        else:
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"

        cost_text += "📅 Введите дату осмотра:"

        await state.update_data(cost=int(total_cost))
        await state.set_state(Form.waiting_for_date)
        await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")

    # ТЕПЛОВИЗОР
    elif user_data.get('thermal_area'):
        object_type = user_data.get('thermal_object')
        area = user_data.get('thermal_area')
        base_price, travel_cost, total_cost = calculate_thermal_cost(object_type, area, distance_km, in_city)

        cost_text = "🌡️ <b>Тепловизионное обследование</b>\n━━━━━━━━━━━━━━\n\n"

        if lat is not None:
            cost_text += f"📌 Распознан: {full_address}\n\n"

        cost_text += f"📍 Адрес: {address}\n"
        cost_text += f"📏 Расстояние: {distance_km} км\n\n"

        if travel_cost > 0:
            cost_text += f"💵 Базовая: {int(base_price)} ₽\n"
            cost_text += f"🚗 Выезд: {int(travel_cost)} ₽\n\n"
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"
        else:
            cost_text += f"💎 ИТОГО: {int(total_cost)} ₽\n\n"

        cost_text += "📅 Введите дату осмотра:"

        await state.update_data(cost=int(total_cost))
        await state.set_state(Form.waiting_for_date)
        await message.answer(cost_text, reply_markup=get_back_button(), parse_mode="HTML")


@dp.message(Form.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    date = message.text.strip()
    await state.update_data(date=date)

    user_data = await state.get_data()
    service = user_data.get('service')
    mortgage_purpose = user_data.get('mortgage_purpose')

    if service == 'service_1':
        if mortgage_purpose:
            if mortgage_purpose in ["Оформление ипотеки", "Рефинансирование"]:
                docs_text = (
                    "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
                    "📧 7511327@mail.ru\n\n"
                    "📋 Документы:\n"
                    "1. Выписка ЕГРН\n"
                    "2. Техпаспорт/Техплан\n"
                    "3. Паспорта собственников и заемщика"
                )
            else:
                object_type = user_data.get('object_type')
                if object_type == "Квартира, комната":
                    docs_text = (
                        "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
                        "📧 7511327@mail.ru\n\n"
                        "📋 Для квартиры:\n"
                        "1. Договор ДДУ/уступки/купли-продажи\n"
                        "2. Акт приема-передачи\n"
                        "3. Паспорт заемщика"
                    )
                elif object_type == "Жилой дом/садовый дом/таунхаус":
                    docs_text = (
                        "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
                        "📧 7511327@mail.ru\n\n"
                        "📋 Для дома:\n"
                        "1. Выписка ЕГРН (дом + участок)\n"
                        "2. Технический план\n"
                        "3. Паспорт заемщика"
                    )
                else:
                    docs_text = (
                        "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
                        "📧 7511327@mail.ru\n\n"
                        "📋 Документы:\n"
                        "1. Выписка ЕГРН\n"
                        "2. Паспорт заемщика"
                    )
        else:
            docs_text = (
                "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
                "📧 7511327@mail.ru\n\n"
                "📋 Документы:\n"
                "1. Выписка ЕГРН\n"
                "2. Паспорт заказчика"
            )
    elif service == 'service_2':
        docs_text = (
            "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
            "📧 7511327@mail.ru\n\n"
            "📋 Документы:\n"
            "1. Выписка ЕГРН\n"
            "2. Паспорт заказчика\n"
            "3. Акт от УК\n"
            "4. Техпаспорт (при наличии)"
        )
    else:
        docs_text = (
            "📎 <b>Прикрепите документы</b>\n━━━━━━━━━━━━━━\n\n"
            "📧 7511327@mail.ru"
        )

    await state.set_state(Form.waiting_for_documents)
    await message.answer(docs_text, reply_markup=get_documents_menu(), parse_mode="HTML")


# INSURANCE HANDLERS
@dp.callback_query(F.data.startswith("insurance_"))
async def process_insurance_type(callback: CallbackQuery, state: FSMContext):
    if callback.data == "insurance_new":
        await state.update_data(insurance_type="new")
        await state.set_state(Form.waiting_for_insurance_coverage)
        text = "🆕 <b>Новая ипотека</b>\n━━━━━━━━━━━━━━\n\n🛡️ Что страхуем?"
        await callback.message.edit_text(text, reply_markup=get_insurance_coverage_menu(), parse_mode="HTML")
    elif callback.data == "insurance_renewal":
        await state.update_data(insurance_type="renewal")
        await state.set_state(Form.waiting_for_insurance_coverage)
        text = "🔄 <b>Продление договора</b>\n━━━━━━━━━━━━━━\n\n🛡️ Что страхуем?"
        await callback.message.edit_text(text, reply_markup=get_insurance_coverage_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("coverage_"))
async def process_insurance_coverage(callback: CallbackQuery, state: FSMContext):
    coverage = callback.data.split("_")[1]
    coverage_names = {
        "property": "Недвижимость (конструктив)",
        "life": "Жизнь"
    }
    coverage_name = coverage_names.get(coverage)
    await state.update_data(insurance_coverage=coverage, insurance_coverage_name=coverage_name)
    await state.set_state(Form.waiting_for_insurance_object)

    text = f"🛡️ Страхование: {coverage_name}\n━━━━━━━━━━━━━━\n\n🏠 Объект:"
    await callback.message.edit_text(text, reply_markup=get_insurance_object_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("ins_object_"))
async def process_insurance_object(callback: CallbackQuery, state: FSMContext):
    object_id = callback.data.split("_")[2]
    object_names = {
        "1": "Квартира, комната",
        "2": "Жилой дом/садовый дом/таунхаус"
    }
    object_type = object_names.get(object_id)
    await state.update_data(insurance_object=object_type)
    await state.set_state(Form.waiting_for_mortgage_balance)

    text = f"🏠 Объект: {object_type}\n━━━━━━━━━━━━━━\n\n💰 Введите остаток по ипотеке (в рублях):"
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()


@dp.message(Form.waiting_for_mortgage_balance)
async def process_mortgage_balance(message: Message, state: FSMContext):
    try:
        balance = float(message.text.strip().replace(" ", "").replace(",", "."))
        if balance <= 0:
            await message.answer("❌ Введите положительную сумму")
            return

        await state.update_data(mortgage_balance=balance)
        user_data = await state.get_data()

        object_type = user_data.get('insurance_object')
        insurance_cost = calculate_insurance_cost(object_type, balance)

        await state.update_data(insurance_cost=insurance_cost)

        text = (
            f"💸 <b>Предварительный расчет</b>\n━━━━━━━━━━━━━━\n\n"
            f"💎 Стоимость полиса: {insurance_cost} ₽\n\n"
            f"Это предварительный расчёт.\n"
            f"Для точного расчёта прикрепите документы\n\n"
        )

        insurance_type = user_data.get('insurance_type')
        insurance_coverage = user_data.get('insurance_coverage')

        if insurance_type == "new":
            text += "📋 Документы:\n"
            text += "1. Паспорт (фото и прописка)\n"
            text += "2. Выписка ЕГРН\n"
            text += "3. Отчёт об оценке\n"
            text += "4. Кредитный договор\n"
        else:
            text += "📋 Документы:\n"
            text += "1. Предыдущий страховой договор\n"
            text += "2. Действующий кредитный договор\n"

        if insurance_coverage == "life":
            text += "\nДополнительно укажите:\n"
            text += "• Профессия\n"
            text += "• Состояние здоровья\n"
            text += "• Занятие спортом\n"

        text += "\n📧 7511327@mail.ru"

        await state.set_state(Form.waiting_for_insurance_documents)
        await message.answer(text, reply_markup=get_documents_menu(), parse_mode="HTML")

    except ValueError:
        await message.answer("❌ Введите корректную сумму")


# DEALS HANDLERS
@dp.callback_query(F.data.startswith("deals_"))
async def process_deals_service(callback: CallbackQuery, state: FSMContext):
    deals_type = callback.data.split("_")[1]

    if deals_type == "egrn":
        admin_text = "📑 <b>Запрос выписки из ЕГРН</b>"
        text = (
            "📑 <b>Выписки из ЕГРН</b>\n━━━━━━━━━━━━━━\n\n"
            "🤖 Перейдите в бота:\n\n"
            "👉 @EGRN_365bot"
        )
    else:
        admin_text = "📊 <b>Запрос анализа сделок</b>"
        text = (
            "📊 <b>Анализ сделок</b>\n━━━━━━━━━━━━━━\n\n"
            "🤖 Перейдите в бота:\n\n"
            "👉 @realestate_deals_bot"
        )

    await send_to_admins(admin_text, get_user_info(callback.from_user))

    await callback.message.edit_text(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
    await state.clear()
    await callback.answer()


# DOCUMENTS HANDLERS
@dp.callback_query(F.data.in_(["attach_docs", "submit_no_docs"]))
async def process_documents_buttons(callback: CallbackQuery, state: FSMContext):
    if callback.data == "attach_docs":
        current_state = await state.get_state()
        if current_state == Form.waiting_for_insurance_documents:
            text = "📎 <b>Прикрепление документов</b>\n━━━━━━━━━━━━━━\n\n📤 Отправьте документы\n\n✅ После - нажмите /done"
        else:
            text = "📎 <b>Прикрепление документов</b>\n━━━━━━━━━━━━━━\n\n📤 Отправьте документы\n\n✅ После - нажмите /done"
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
    else:
        user_data = await state.get_data()

        admin_text = await format_admin_message(user_data)
        await send_to_admins(admin_text, get_user_info(callback.from_user))

        text = (
            "✅ <b>Заявка принята!</b>\n━━━━━━━━━━━━━━\n\n"
            "📞 Специалист свяжется с вами в ближайшее время"
        )
        await callback.message.edit_text(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
        await callback.answer()


@dp.message(Form.waiting_for_documents, F.document | F.photo)
async def handle_documents(message: Message, state: FSMContext):
    await message.answer("✅ Документ получен")


@dp.message(Form.waiting_for_insurance_documents, F.document | F.photo)
async def handle_insurance_documents(message: Message, state: FSMContext):
    await message.answer("✅ Документ получен")


@dp.message(Form.waiting_for_insurance_documents)
async def handle_insurance_text_info(message: Message, state: FSMContext):
    await message.answer("✅ Информация сохранена")


@dp.message(Command("done"))
async def cmd_done(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [Form.waiting_for_documents, Form.waiting_for_insurance_documents]:
        user_data = await state.get_data()

        admin_text = await format_admin_message(user_data)
        admin_text += "\n\n📎 Пользователь прикрепил документы"
        await send_to_admins(admin_text, get_user_info(message.from_user))

        if current_state == Form.waiting_for_insurance_documents:
            text = (
                "✅ <b>Заявка на страхование принята!</b>\n━━━━━━━━━━━━━━\n\n"
                "💼 Специалист рассчитает точную стоимость и свяжется с вами\n\n"
                "📞 Время обработки:\n"
                "• Рабочие дни 9-18: до 30 мин\n"
                "• Нерабочее время: на следующий день"
            )
        else:
            text = "✅ <b>Заявка принята!</b>\n━━━━━━━━━━━━━━\n\n📞 Специалист свяжется с вами"

        await message.answer(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
        await state.clear()
    else:
        await message.answer("⚠️ Нет активной заявки")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())