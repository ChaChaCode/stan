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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class Form(StatesGroup):
    waiting_for_service = State()
    waiting_for_purpose = State()
    waiting_for_bank = State()
    waiting_for_mortgage_purpose = State()
    waiting_for_object_type = State()
    waiting_for_report_type = State()
    waiting_for_flood_object = State()
    waiting_for_flood_rooms = State()
    waiting_for_address = State()
    waiting_for_date = State()
    waiting_for_documents = State()
    # БТИ
    waiting_for_bti_service = State()
    waiting_for_bti_passport_action = State()
    waiting_for_bti_plan_action = State()
    waiting_for_bti_plan_object = State()
    waiting_for_bti_survey_action = State()
    waiting_for_bti_survey_service = State()
    waiting_for_bti_acts_action = State()
    waiting_for_bti_acts_service = State()
    # Экспертиза
    waiting_for_expertise_type = State()
    waiting_for_expertise_stage = State()
    waiting_for_expertise_object = State()
    waiting_for_expertise_status = State()
    waiting_for_expertise_goals = State()
    waiting_for_expertise_description = State()
    waiting_for_expertise_photos = State()
    # Приёмка
    waiting_for_acceptance_finish = State()
    waiting_for_acceptance_material = State()
    waiting_for_acceptance_area = State()
    # Обследование перед покупкой
    waiting_for_inspection_area = State()
    waiting_for_inspection_material = State()
    waiting_for_inspection_finish = State()
    # Тепловизор
    waiting_for_thermal_object = State()
    waiting_for_thermal_area = State()
    # Страхование
    waiting_for_insurance_type = State()
    waiting_for_insurance_coverage = State()
    waiting_for_insurance_object = State()
    waiting_for_mortgage_balance = State()
    waiting_for_insurance_life_info = State()
    waiting_for_insurance_documents = State()
    # Сделки
    waiting_for_deals_service = State()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def round_to_hundreds(value):
    """Округление до сотен: 2927→2900, 2957→3000"""
    return round(value / 100) * 100


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def is_in_chelyabinsk(full_address: str) -> bool:
    if not full_address:
        return False
    addr = full_address.lower()
    if 'челябинск,' in addr or 'челябинск ' in addr:
        if 'челябинская область' in addr and 'челябинск,' not in addr:
            return False
        return True
    return False


async def geocode_address(address: str):
    try:
        formatted = address if any(c in address.lower() for c in ['челябинск', 'миасс', 'златоуст', 'копейск', 'магнитогорск']) else f"Челябинск, {address}"
        async with aiohttp.ClientSession() as session:
            params = {"apikey": "61f30bb9-04d7-4eb9-8636-908c6f611e4c", "geocode": formatted, "format": "json", "results": 1}
            async with session.get("https://geocode-maps.yandex.ru/1.x/", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    members = data.get('response', {}).get('GeoObjectCollection', {}).get('featureMember', [])
                    if members:
                        obj = members[0]['GeoObject']
                        lon, lat = map(float, obj['Point']['pos'].split())
                        full_addr = obj.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', '')
                        return lat, lon, full_addr
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
    return None, None, None


def get_user_info(user) -> str:
    info = f"ID: <code>{user.id}</code>\n"
    if user.username:
        info += f"Username: @{user.username}\n"
        info += f"Профиль: <a href='https://t.me/{user.username}'>Открыть чат</a>\n"
    else:
        info += f"Профиль: <a href='tg://user?id={user.id}'>Открыть чат</a>\n"
    name = user.first_name or ''
    if user.last_name:
        name += f" {user.last_name}"
    info += f"Имя: {name or 'Не указано'}"
    return info


def get_address_hint() -> str:
    return (
        "Введите адрес в формате:\n\n"
        "Город, улица, дом, кв (например: Челябинск, проспект Ленина, 21 44)\n"
        "или\n"
        "Кадастровый номер (например: 74:27:080301:1234)\n\n"
        "Если не указать город, автоматически добавится Челябинск"
    )


async def send_to_admins(text: str, user_info: str = None):
    msg = f"🔔 <b>НОВАЯ ЗАЯВКА</b>\n{'━' * 20}\n\n{text}"
    if user_info:
        msg += f"\n\n👤 <b>Клиент:</b>\n{user_info}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Admin {admin_id} error: {e}")


async def send_documents_to_admins(documents: list, user_info: str, order_info: str):
    if not documents:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"📎 <b>Документы к заявке:</b>\n{'━' * 20}\n\n{order_info}\n\n👤 <b>Клиент:</b>\n{user_info}", parse_mode="HTML", disable_web_page_preview=True)
            for doc in documents:
                try:
                    if doc['type'] == 'photo':
                        await bot.send_photo(admin_id, doc['file_id'], caption=doc.get('caption', ''))
                    elif doc['type'] == 'document':
                        await bot.send_document(admin_id, doc['file_id'], caption=doc.get('caption', ''))
                except Exception as e:
                    logger.error(f"Doc send error: {e}")
        except Exception as e:
            logger.error(f"Admin {admin_id} docs error: {e}")


async def send_price_image(message_or_callback, image_name: str, caption: str = None):
    image_path = os.path.join(SCRIPT_DIR, image_name)
    if os.path.exists(image_path):
        try:
            photo = FSInputFile(image_path)
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.answer_photo(photo, caption=caption)
            else:
                await message_or_callback.answer_photo(photo, caption=caption)
        except Exception as e:
            logger.error(f"Price image error: {e}")


# ========== КЛАВИАТУРЫ ==========

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◆ Оценка недвижимости", callback_data="service_1")],
        [InlineKeyboardButton(text="◆ Оценка ущерба после затопления", callback_data="service_2")],
        [InlineKeyboardButton(text="◆ БТИ / Кадастр / Межевание", callback_data="service_3")],
        [InlineKeyboardButton(text="◆ Строительно-техническая экспертиза / Обследования", callback_data="service_4")],
        [InlineKeyboardButton(text="◆ Ипотечное страхование", callback_data="service_5")],
        [InlineKeyboardButton(text="◆ Сделки с недвижимостью", callback_data="service_6")],
        [InlineKeyboardButton(text="✉ Написать нам напрямую", url="https://t.me/+79080415241")]
    ])


def get_main_menu_button():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]])


def get_back_and_main_buttons(back_callback="back"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data=back_callback)],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_documents_menu(back_callback="back"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Прикрепить документы", callback_data="attach_docs")],
        [InlineKeyboardButton(text="✓ Отправить заявку без документов", callback_data="submit_order")],
        [InlineKeyboardButton(text="◀ Назад", callback_data=back_callback)],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_finish_docs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✓ Готово, отправить заявку", callback_data="submit_order")],
        [InlineKeyboardButton(text="📎 Добавить ещё", callback_data="add_more_docs")]
    ])


# === ОЦЕНКА НЕДВИЖИМОСТИ ===

def get_evaluation_purpose_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Для банка (ипотека)", callback_data="purpose_bank")],
        [InlineKeyboardButton(text="Для органов опеки", callback_data="purpose_opeka")],
        [InlineKeyboardButton(text="Для нотариуса", callback_data="purpose_notary")],
        [InlineKeyboardButton(text="Для суда", callback_data="purpose_court")],
        [InlineKeyboardButton(text="Для купли-продажи", callback_data="purpose_sale")],
        [InlineKeyboardButton(text="Иная цель", callback_data="purpose_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_banks_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сбербанк", callback_data="bank_sber"), InlineKeyboardButton(text="ВТБ", callback_data="bank_vtb")],
        [InlineKeyboardButton(text="Дом.РФ", callback_data="bank_domrf"), InlineKeyboardButton(text="Россельхозбанк", callback_data="bank_rshb")],
        [InlineKeyboardButton(text="Альфа-Банк", callback_data="bank_alfa"), InlineKeyboardButton(text="Совкомбанк", callback_data="bank_sovkom")],
        [InlineKeyboardButton(text="Газпромбанк", callback_data="bank_gazprom"), InlineKeyboardButton(text="Промсвязьбанк (ПСБ)", callback_data="bank_psb")],
        [InlineKeyboardButton(text="ПримСоцБанк", callback_data="bank_primsoc"), InlineKeyboardButton(text="Уралсиб", callback_data="bank_uralsib")],
        [InlineKeyboardButton(text="АК Барс Банк", callback_data="bank_akbars"), InlineKeyboardButton(text="Райффайзенбанк", callback_data="bank_raif")],
        [InlineKeyboardButton(text="Челябинвестбанк", callback_data="bank_chelinvest"), InlineKeyboardButton(text="УБРиР", callback_data="bank_ubrir")],
        [InlineKeyboardButton(text="Ипотека24", callback_data="bank_ipoteka24"), InlineKeyboardButton(text="Новикомбанк", callback_data="bank_novikom")],
        [InlineKeyboardButton(text="Евразийский банк", callback_data="bank_evraz"), InlineKeyboardButton(text="Росвоенипотека", callback_data="bank_rosvoen")],
        [InlineKeyboardButton(text="Уралпромбанк", callback_data="bank_uralprom"), InlineKeyboardButton(text="Другой", callback_data="bank_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_purpose")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_mortgage_purpose_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оформление ипотеки", callback_data="mpurpose_new")],
        [InlineKeyboardButton(text="Оформление закладной после сдачи объекта в эксплуатацию", callback_data="mpurpose_zaklad")],
        [InlineKeyboardButton(text="Рефинансирование", callback_data="mpurpose_refi")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bank")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_object_types_menu(back_callback="back_to_mpurpose"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира, комната", callback_data="obj_flat")],
        [InlineKeyboardButton(text="Земельный участок", callback_data="obj_land")],
        [InlineKeyboardButton(text="Жилой дом/садовый дом/таунхаус/квартира с земельным участком", callback_data="obj_house")],
        [InlineKeyboardButton(text="Нежилое помещение (встроенное)", callback_data="obj_commercial")],
        [InlineKeyboardButton(text="Нежилое здание с земельным участком", callback_data="obj_building")],
        [InlineKeyboardButton(text="Гараж", callback_data="obj_garage")],
        [InlineKeyboardButton(text="Машиноместо", callback_data="obj_parking")],
        [InlineKeyboardButton(text="◀ Назад", callback_data=back_callback)],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_report_type_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Краткая справка", callback_data="report_short")],
        [InlineKeyboardButton(text="Отчёт об оценке", callback_data="report_full")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_purpose")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# === ЗАТОПЛЕНИЕ ===

def get_flood_objects_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира, комната", callback_data="flood_flat")],
        [InlineKeyboardButton(text="Жилой дом/садовый дом/таунхаус", callback_data="flood_house")],
        [InlineKeyboardButton(text="Нежилое помещение", callback_data="flood_commercial")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# === БТИ ===

def get_bti_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выписка из технического паспорта", callback_data="bti_extract")],
        [InlineKeyboardButton(text="Технический паспорт", callback_data="bti_passport")],
        [InlineKeyboardButton(text="Технический план", callback_data="bti_plan")],
        [InlineKeyboardButton(text="Межевание (земля)", callback_data="bti_survey")],
        [InlineKeyboardButton(text="Акты, справки", callback_data="bti_acts")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_bti_passport_action_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Узнать стоимость", callback_data="bti_passport_price")],
        [InlineKeyboardButton(text="Ввести адрес", callback_data="bti_passport_address")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_bti_plan_action_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Узнать стоимость", callback_data="bti_plan_price")],
        [InlineKeyboardButton(text="Выберите объект", callback_data="bti_plan_object")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_bti_plan_objects_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира, комната", callback_data="btiplan_flat")],
        [InlineKeyboardButton(text="Жилой дом/садовый дом/таунхаус", callback_data="btiplan_house")],
        [InlineKeyboardButton(text="Нежилое помещение (встроенное)", callback_data="btiplan_commercial")],
        [InlineKeyboardButton(text="Нежилое здание", callback_data="btiplan_building")],
        [InlineKeyboardButton(text="Гараж", callback_data="btiplan_garage")],
        [InlineKeyboardButton(text="Раздел дома", callback_data="btiplan_split_house")],
        [InlineKeyboardButton(text="Раздел/объединение помещений", callback_data="btiplan_split_rooms")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti_plan")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_bti_survey_action_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Узнать стоимость", callback_data="bti_survey_price")],
        [InlineKeyboardButton(text="Выберите услугу", callback_data="bti_survey_service")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_survey_services_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Уточнение границ зем. участка", callback_data="surv_borders")],
        [InlineKeyboardButton(text="Раздел/объединение участка", callback_data="surv_split")],
        [InlineKeyboardButton(text="Схема для КУиЗО", callback_data="surv_kuizo")],
        [InlineKeyboardButton(text="Перераспределение (межевой)", callback_data="surv_redistr")],
        [InlineKeyboardButton(text="Перераспределение (схема + межевой)", callback_data="surv_redistr_full")],
        [InlineKeyboardButton(text="Схема под гараж", callback_data="surv_garage")],
        [InlineKeyboardButton(text="Межевой по распоряжению", callback_data="surv_order")],
        [InlineKeyboardButton(text="Межевой для суда", callback_data="surv_court")],
        [InlineKeyboardButton(text="Межевой на сервитут", callback_data="surv_servitude")],
        [InlineKeyboardButton(text="Другое", callback_data="surv_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti_survey")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_bti_acts_action_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Узнать стоимость", callback_data="bti_acts_price")],
        [InlineKeyboardButton(text="Выберите услугу", callback_data="bti_acts_service")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_acts_services_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Документы на акт ввода до 1500 кв.м", callback_data="acts_input")],
        [InlineKeyboardButton(text="На гараж", callback_data="acts_garage")],
        [InlineKeyboardButton(text="Акт сноса", callback_data="acts_demolish")],
        [InlineKeyboardButton(text="Справка о местоположении (комната)", callback_data="acts_location")],
        [InlineKeyboardButton(text="Справка о стоимости", callback_data="acts_cost")],
        [InlineKeyboardButton(text="Заполнение уведомлений (снос, перепланировка и т.д.)", callback_data="acts_notify")],
        [InlineKeyboardButton(text="Другое", callback_data="acts_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_bti_acts")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# === ЭКСПЕРТИЗА ===

def get_expertise_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Строительно-техническая экспертиза", callback_data="exp_build")],
        [InlineKeyboardButton(text="Приемка жилого дома от застройщика", callback_data="exp_accept")],
        [InlineKeyboardButton(text="Техническое обследование жилого дома перед покупкой", callback_data="exp_inspect")],
        [InlineKeyboardButton(text="Тепловизионное обследование", callback_data="exp_thermal")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_expertise_stage_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Уже идёт судебный процесс", callback_data="expstage_court")],
        [InlineKeyboardButton(text="Подготовка претензии / досудебное урегулирование", callback_data="expstage_pretrial")],
        [InlineKeyboardButton(text="Затрудняюсь ответить", callback_data="expstage_unknown")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_expertise")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_expertise_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◆ Квартира", callback_data="expobj_flat")],
        [InlineKeyboardButton(text="◆ Индивидуальный жилой дом / коттедж", callback_data="expobj_house")],
        [InlineKeyboardButton(text="◆ Помещение / офис / коммерческий объект", callback_data="expobj_commercial")],
        [InlineKeyboardButton(text="◆ Кровля", callback_data="expobj_roof")],
        [InlineKeyboardButton(text="◆ Фундамент", callback_data="expobj_foundation")],
        [InlineKeyboardButton(text="◆ Другое (ввести свой вариант)", callback_data="expobj_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_exp_stage")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_expertise_status_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◆ Построен", callback_data="expstat_built")],
        [InlineKeyboardButton(text="◆ В процессе строительства", callback_data="expstat_building")],
        [InlineKeyboardButton(text="◆ После ремонта / реконструкции", callback_data="expstat_renovated")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_exp_object")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_expertise_goals_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◆ Выявить строительные дефекты и нарушения", callback_data="expgoal_defects")],
        [InlineKeyboardButton(text="◆ Рассчитать стоимость устранения дефектов", callback_data="expgoal_cost")],
        [InlineKeyboardButton(text="◆ Оценить объём выполненных/невыполненных работ", callback_data="expgoal_volume")],
        [InlineKeyboardButton(text="◆ Проверить соответствие нормативной документации", callback_data="expgoal_docs")],
        [InlineKeyboardButton(text="◆ Подтвердить или опровергнуть претензии другой стороны", callback_data="expgoal_claims")],
        [InlineKeyboardButton(text="◆ Провести комплексное обследование", callback_data="expgoal_complex")],
        [InlineKeyboardButton(text="◆ Другое (ввести свой вариант)", callback_data="expgoal_other")],
        [InlineKeyboardButton(text="✓ Продолжить", callback_data="expgoal_done")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_exp_status")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# Приёмка от застройщика
def get_acceptance_finish_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Черновая (без отделки)", callback_data="accfin_rough")],
        [InlineKeyboardButton(text="Предчистовая", callback_data="accfin_pre")],
        [InlineKeyboardButton(text="Чистовая (с отделкой)", callback_data="accfin_final")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_expertise")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_acceptance_material_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кирпич", callback_data="accmat_brick")],
        [InlineKeyboardButton(text="Ж/б панели", callback_data="accmat_panel")],
        [InlineKeyboardButton(text="Блочный (газоблок, пеноблок и др)", callback_data="accmat_block")],
        [InlineKeyboardButton(text="Дерево", callback_data="accmat_wood")],
        [InlineKeyboardButton(text="Другой", callback_data="accmat_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_acc_finish")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_acceptance_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 150 кв.м.", callback_data="accarea_150")],
        [InlineKeyboardButton(text="150-250 кв.м.", callback_data="accarea_250")],
        [InlineKeyboardButton(text="250-500 кв.м.", callback_data="accarea_500")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_acc_material")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# Обследование перед покупкой
def get_inspection_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 150 кв.м.", callback_data="insparea_150")],
        [InlineKeyboardButton(text="150-250 кв.м.", callback_data="insparea_250")],
        [InlineKeyboardButton(text="250-350 кв.м.", callback_data="insparea_350")],
        [InlineKeyboardButton(text="свыше 350 кв.м.", callback_data="insparea_350plus")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_expertise")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_inspection_material_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кирпич", callback_data="inspmat_brick")],
        [InlineKeyboardButton(text="Ж/б панели", callback_data="inspmat_panel")],
        [InlineKeyboardButton(text="Блочный (газоблок, пеноблок и др)", callback_data="inspmat_block")],
        [InlineKeyboardButton(text="Дерево", callback_data="inspmat_wood")],
        [InlineKeyboardButton(text="Другой", callback_data="inspmat_other")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_insp_area")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_inspection_finish_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Черновая (без отделки)", callback_data="inspfin_rough")],
        [InlineKeyboardButton(text="Предчистовая (стены оштукатурены)", callback_data="inspfin_pre")],
        [InlineKeyboardButton(text="Чистовая (с отделкой)", callback_data="inspfin_final")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_insp_material")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# Тепловизор
def get_thermal_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира", callback_data="thermobj_flat")],
        [InlineKeyboardButton(text="Жилой дом", callback_data="thermobj_house")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_expertise")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_thermal_area_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="до 100 кв.м.", callback_data="thermarea_100")],
        [InlineKeyboardButton(text="100-200 кв.м.", callback_data="thermarea_200")],
        [InlineKeyboardButton(text="200-300 кв.м.", callback_data="thermarea_300")],
        [InlineKeyboardButton(text="свыше 300 кв.м.", callback_data="thermarea_300plus")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_therm_object")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# Страхование
def get_insurance_type_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Новая ипотека", callback_data="ins_new")],
        [InlineKeyboardButton(text="Продление действующего договора страхования", callback_data="ins_renew")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_insurance_coverage_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Недвижимость (конструктив)", callback_data="inscov_property")],
        [InlineKeyboardButton(text="Жизнь", callback_data="inscov_life")],
        [InlineKeyboardButton(text="Оба варианта", callback_data="inscov_both")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_ins_type")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


def get_insurance_object_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира, комната", callback_data="insobj_flat")],
        [InlineKeyboardButton(text="Жилой дом/садовый дом/таунхаус", callback_data="insobj_house")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_ins_coverage")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# Сделки
def get_deals_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выписки из ЕГРН", callback_data="deals_egrn")],
        [InlineKeyboardButton(text="Анализ сделок за квартал", callback_data="deals_analysis")],
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")],
        [InlineKeyboardButton(text="◆ Главное меню", callback_data="main_menu")]
    ])


# ========== СЛОВАРИ ==========

BANK_NAMES = {
    "sber": "Сбербанк", "vtb": "ВТБ", "domrf": "Дом.РФ", "rshb": "Россельхозбанк",
    "alfa": "Альфа-Банк", "sovkom": "Совкомбанк", "gazprom": "Газпромбанк",
    "psb": "Промсвязьбанк (ПСБ)", "primsoc": "ПримСоцБанк", "uralsib": "Уралсиб",
    "akbars": "АК Барс Банк", "raif": "Райффайзенбанк", "chelinvest": "Челябинвестбанк",
    "ubrir": "УБРиР", "ipoteka24": "Ипотека24", "novikom": "Новикомбанк",
    "evraz": "Евразийский банк", "rosvoen": "Росвоенипотека", "uralprom": "Уралпромбанк",
    "other": "Другой"
}

OBJECT_NAMES = {
    "flat": "Квартира, комната",
    "land": "Земельный участок",
    "house": "Жилой дом/садовый дом/таунхаус/квартира с земельным участком",
    "commercial": "Нежилое помещение (встроенное)",
    "building": "Нежилое здание с земельным участком",
    "garage": "Гараж",
    "parking": "Машиноместо"
}

# Группы банков по ТЗ
BANK_GROUP_CHEAP = ['sber', 'rshb', 'chelinvest', 'rosvoen']  # 2500 для квартиры при оформлении ипотеки
BANK_GROUP_SPECIAL = ['vtb', 'domrf', 'alfa', 'primsoc']  # Особые условия


# ========== РАСЧЁТ СТОИМОСТИ ==========

def calculate_mortgage_cost(bank_code, obj_code, mpurpose_code, distance_km, in_city):
    """
    Расчёт стоимости оценки для банка по ТЗ
    
    ✅ ИСПРАВЛЕНО: Цены для земельного участка при оформлении ипотеки
    """
    
    # Расчёт выезда
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    # Базовая стоимость по ТЗ
    if mpurpose_code == 'new':  # Оформление ипотеки
        if obj_code == 'flat':  # Квартира, комната
            base = 2500 if bank_code in BANK_GROUP_CHEAP else 2900
            
        elif obj_code == 'land':  # ✅ ИСПРАВЛЕНО: Земельный участок
            # Для земельного участка при новой ипотеке применяются цены как для закладной
            if bank_code in BANK_GROUP_SPECIAL:
                base = 4000
            else:
                base = 3000
                
        elif obj_code == 'house':  # Жилой дом
            base = 2500 if bank_code in BANK_GROUP_CHEAP else 2900
            
        elif obj_code == 'commercial':  # Нежилое помещение
            base = 6000
            
        elif obj_code == 'building':  # Нежилое здание
            base = 7000
            
        elif obj_code in ['garage', 'parking']:  # Гараж, машиноместо
            base = 3500
        else:
            base = 2900
            
    elif mpurpose_code == 'zaklad':  # Оформление закладной
        if bank_code in BANK_GROUP_SPECIAL:
            base = 4000
        else:
            base = 3000
            
    elif mpurpose_code == 'refi':  # Рефинансирование
        if bank_code in BANK_GROUP_SPECIAL:
            base = 6900
        else:
            base = 5900
    else:
        base = 2900
    
    total = base + travel
    return base, travel, total


def calculate_other_cost(obj_code, report_code, distance_km, in_city):
    """Расчёт стоимости оценки для опеки/нотариуса/суда/продажи/иное по ТЗ"""
    
    if report_code == 'short':  # Краткая справка
        if obj_code in ['flat', 'land', 'garage', 'parking']:  # Пункты 1, 2, 6, 7
            return 1000, 0, 1000
        else:  # Пункты 3, 4, 5
            return 1500, 0, 1500
    
    # Отчёт об оценке
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    prices = {
        'flat': 2500,       # Пункт 1
        'land': 3000,       # Пункт 2
        'house': 5900,      # Пункт 3
        'commercial': 6000, # Пункт 4
        'building': 7000,   # Пункт 5
        'garage': 3500,     # Пункт 6
        'parking': 3500     # Пункт 7
    }
    base = prices.get(obj_code, 3000)
    return base, travel, base + travel


def calculate_flood_cost(obj_code, rooms, distance_km, in_city):
    """Расчёт стоимости оценки ущерба от затопления по ТЗ"""
    
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    if obj_code == 'commercial':  # Нежилое помещение
        base = 7000
        room_price = 2000
    else:  # Квартира, дом
        base = 6000
        room_price = 1500
    
    rooms_cost = (rooms - 1) * room_price if rooms > 1 else 0
    total = base + rooms_cost + travel
    return base, rooms_cost, travel, total


def calculate_acceptance_cost(area_code, distance_km, in_city):
    """Расчёт стоимости приёмки от застройщика по ТЗ"""
    
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    prices = {'150': 15000, '250': 18000, '500': 20000}
    base = prices.get(area_code, 15000)
    return base, travel, base + travel


def calculate_inspection_cost(area_code, distance_km, in_city):
    """Расчёт стоимости обследования перед покупкой по ТЗ"""
    
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    prices = {'150': 10000, '250': 12000, '350': 15000, '350plus': 18000}
    base = prices.get(area_code, 10000)
    return base, travel, base + travel


def calculate_thermal_cost(obj_code, area_code, distance_km, in_city):
    """Расчёт стоимости тепловизионного обследования по ТЗ"""
    
    if in_city:
        travel = 0
    else:
        travel = round_to_hundreds(distance_km * 35)
    
    if obj_code == 'flat':
        prices = {'100': 3000, '200': 3500, '300': 4000, '300plus': 4500}
    else:  # house
        prices = {'100': 5000, '200': 5500, '300': 6000, '300plus': 6500}
    
    base = prices.get(area_code, 3000)
    return base, travel, base + travel


def calculate_insurance_cost(obj_code, balance):
    """Расчёт стоимости страхования по ТЗ"""
    rate = 0.001 if obj_code == 'flat' else 0.003
    return round(balance * rate, 2)


# ========== ФОРМИРОВАНИЕ ЗАЯВКИ ==========

async def format_order_text(data: dict) -> str:
    service = data.get('service_type', '')

    if service == 'evaluation':
        bank = data.get('bank_name', '')
        purpose = data.get('purpose_name', '')
        mpurpose = data.get('mpurpose_name', '')

        text = "◆ <b>ОЦЕНКА НЕДВИЖИМОСТИ</b>\n\n"
        if bank:
            text += f"Банк: {bank}\n"
            text += f"Цель: {mpurpose}\n"
        else:
            text += f"Цель: {purpose}\n"
            text += f"Форма: {data.get('report_name', '')}\n"

        text += f"Объект: {data.get('object_name', '')}\n"
        text += f"Адрес: {data.get('address', '')}\n"
        if data.get('full_address'):
            text += f"Определён: {data.get('full_address')}\n"
        text += f"Расстояние: {data.get('distance', 0)} км\n"
        text += f"Дата: {data.get('date', '')}\n"
        text += f"Стоимость: {data.get('cost', 0)} ₽"

    elif service == 'flood':
        text = "◆ <b>ОЦЕНКА УЩЕРБА ОТ ЗАТОПЛЕНИЯ</b>\n\n"
        text += f"Объект: {data.get('object_name', '')}\n"
        text += f"Помещений: {data.get('rooms', 1)}\n"
        text += f"Адрес: {data.get('address', '')}\n"
        text += f"Расстояние: {data.get('distance', 0)} км\n"
        text += f"Дата: {data.get('date', '')}\n"
        text += f"Стоимость: {data.get('cost', 0)} ₽"

    elif service == 'bti':
        text = "◆ <b>БТИ / КАДАСТР / МЕЖЕВАНИЕ</b>\n\n"
        text += f"Услуга: {data.get('bti_service_name', '')}\n"
        if data.get('bti_object_name'):
            text += f"Объект: {data.get('bti_object_name')}\n"
        if data.get('survey_service_name'):
            text += f"Вид работ: {data.get('survey_service_name')}\n"
        if data.get('acts_service_name'):
            text += f"Услуга: {data.get('acts_service_name')}\n"
        if data.get('address'):
            text += f"Адрес: {data.get('address')}\n"
        if data.get('cost'):
            text += f"Стоимость: {data.get('cost')} ₽"

    elif service == 'expertise':
        text = "◆ <b>ЭКСПЕРТИЗА / ОБСЛЕДОВАНИЕ</b>\n\n"
        text += f"Тип: {data.get('exp_type_name', '')}\n"
        if data.get('exp_stage_name'):
            text += f"Этап: {data.get('exp_stage_name')}\n"
        if data.get('exp_object_name'):
            text += f"Объект: {data.get('exp_object_name')}\n"
        if data.get('exp_status_name'):
            text += f"Статус: {data.get('exp_status_name')}\n"
        if data.get('exp_goals'):
            text += f"Цели: {', '.join(data.get('exp_goals', []))}\n"
        if data.get('exp_description'):
            text += f"Описание: {data.get('exp_description')}\n"
        if data.get('acc_finish_name'):
            text += f"Отделка: {data.get('acc_finish_name')}\n"
        if data.get('acc_material_name'):
            text += f"Материал: {data.get('acc_material_name')}\n"
        if data.get('acc_area_name'):
            text += f"Площадь: {data.get('acc_area_name')}\n"
        if data.get('insp_area_name'):
            text += f"Площадь: {data.get('insp_area_name')}\n"
        if data.get('insp_material_name'):
            text += f"Материал: {data.get('insp_material_name')}\n"
        if data.get('insp_finish_name'):
            text += f"Отделка: {data.get('insp_finish_name')}\n"
        if data.get('therm_object_name'):
            text += f"Объект: {data.get('therm_object_name')}\n"
        if data.get('therm_area_name'):
            text += f"Площадь: {data.get('therm_area_name')}\n"
        if data.get('address'):
            text += f"Адрес: {data.get('address')}\n"
        if data.get('date'):
            text += f"Дата: {data.get('date')}\n"
        if data.get('cost'):
            text += f"Стоимость: {data.get('cost')} ₽"

    elif service == 'insurance':
        text = "◆ <b>ИПОТЕЧНОЕ СТРАХОВАНИЕ</b>\n\n"
        text += f"Тип: {data.get('ins_type_name', '')}\n"
        text += f"Покрытие: {data.get('ins_coverage_name', '')}\n"
        text += f"Объект: {data.get('ins_object_name', '')}\n"
        text += f"Остаток: {data.get('balance', 0):,.0f} ₽\n".replace(',', ' ')
        text += f"Примерная стоимость: {data.get('cost', 0)} ₽"
        if data.get('life_info'):
            text += f"\n\nИнформация для страхования жизни:\n{data.get('life_info')}"

    else:
        text = "◆ <b>ЗАЯВКА</b>\n\n"
        for k, v in data.items():
            if v and not k.startswith('_') and k != 'documents':
                text += f"{k}: {v}\n"

    return text


# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Form.waiting_for_service)
    text = (
        "<b>Независимая экспертная компания «Перспектива» (ООО)</b>\n\n"
        "Этот бот создан, чтобы быстро и удобно оформить любые услуги компании НЭК «Перспектива» без звонков и визитов в офис.\n\n"
        "Через него вы можете:\n"
        "- Быстро оформить заявку\n"
        "- Узнать стоимость услуг\n"
        "- Записаться на удобную дату и время\n"
        "- Отправить документы для заявки\n"
        "- Связаться с нами напрямую\n\n"
        "👇 Выберите услугу:"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def go_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.waiting_for_service)
    text = (
        "<b>Независимая экспертная компания «Перспектива» (ООО)</b>\n\n"
        "Этот бот создан, чтобы быстро и удобно оформить любые услуги компании НЭК «Перспектива» без звонков и визитов в офис.\n\n"
        "Через него вы можете:\n"
        "- Быстро оформить заявку\n"
        "- Узнать стоимость услуг\n"
        "- Записаться на удобную дату и время\n"
        "- Отправить документы для заявки\n"
        "- Связаться с нами напрямую\n\n"
        "👇 Выберите услугу:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.waiting_for_service)
    text = (
        "<b>Независимая экспертная компания «Перспектива» (ООО)</b>\n\n"
        "Этот бот создан, чтобы быстро и удобно оформить любые услуги компании НЭК «Перспектива» без звонков и визитов в офис.\n\n"
        "Через него вы можете:\n"
        "- Быстро оформить заявку\n"
        "- Узнать стоимость услуг\n"
        "- Записаться на удобную дату и время\n"
        "- Отправить документы для заявки\n"
        "- Связаться с нами напрямую\n\n"
        "👇 Выберите услугу:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()


# === ВЫБОР УСЛУГИ ===

@dp.callback_query(F.data.startswith("service_"))
async def select_service(callback: CallbackQuery, state: FSMContext):
    srv = callback.data.split("_")[1]

    if srv == "1":  # Оценка
        await state.update_data(service_type='evaluation')
        await state.set_state(Form.waiting_for_purpose)
        await callback.message.edit_text(
            "<b>Оценка недвижимости</b>\n\n👇 Выберите цель оценки:",
            reply_markup=get_evaluation_purpose_menu(), parse_mode="HTML"
        )

    elif srv == "2":  # Затопление
        await state.update_data(service_type='flood')
        await state.set_state(Form.waiting_for_flood_object)
        await callback.message.edit_text(
            "<b>Оценка ущерба после затопления</b>\n\nКакой объект пострадал?",
            reply_markup=get_flood_objects_menu(), parse_mode="HTML"
        )

    elif srv == "3":  # БТИ
        await state.update_data(service_type='bti')
        await state.set_state(Form.waiting_for_bti_service)
        await callback.message.edit_text(
            "<b>БТИ / Кадастр / Межевание</b>\n\n👇 Выберите услугу:",
            reply_markup=get_bti_menu(), parse_mode="HTML"
        )

    elif srv == "4":  # Экспертиза
        await state.update_data(service_type='expertise')
        await state.set_state(Form.waiting_for_expertise_type)
        await callback.message.edit_text(
            "<b>Строительно-техническая экспертиза / Обследования</b>\n\n👇 Выберите тип услуги:",
            reply_markup=get_expertise_menu(), parse_mode="HTML"
        )

    elif srv == "5":  # Страхование
        await state.update_data(service_type='insurance')
        await state.set_state(Form.waiting_for_insurance_type)
        await callback.message.edit_text(
            "<b>Ипотечное страхование</b>\n\n👇 Выберите тип:",
            reply_markup=get_insurance_type_menu(), parse_mode="HTML"
        )

    elif srv == "6":  # Сделки
        await state.update_data(service_type='deals')
        await state.set_state(Form.waiting_for_deals_service)
        await callback.message.edit_text(
            "<b>Сделки с недвижимостью</b>\n\n👇 Выберите услугу:",
            reply_markup=get_deals_menu(), parse_mode="HTML"
        )

    await callback.answer()


# ========== ОЦЕНКА НЕДВИЖИМОСТИ ==========

@dp.callback_query(F.data == "back_to_purpose")
async def back_to_purpose(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_purpose)
    await callback.message.edit_text(
        "<b>Оценка недвижимости</b>\n\n👇 Выберите цель оценки:",
        reply_markup=get_evaluation_purpose_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("purpose_"))
async def select_purpose(callback: CallbackQuery, state: FSMContext):
    purpose = callback.data.split("_")[1]
    purposes = {
        'bank': 'Для банка (ипотека)', 'opeka': 'Для органов опеки',
        'notary': 'Для нотариуса', 'court': 'Для суда',
        'sale': 'Для купли-продажи', 'other': 'Иная цель'
    }

    await state.update_data(purpose_code=purpose, purpose_name=purposes.get(purpose, ''))

    if purpose == 'bank':
        await state.set_state(Form.waiting_for_bank)
        await callback.message.edit_text(
            "<b>Оценка для банка</b>\n\nВ какой банк будет предоставляться оценка?",
            reply_markup=get_banks_menu(), parse_mode="HTML"
        )
    else:
        await state.set_state(Form.waiting_for_report_type)
        await callback.message.edit_text(
            f"<b>{purposes.get(purpose)}</b>\n\nВ какой форме требуется оценка?",
            reply_markup=get_report_type_menu(), parse_mode="HTML"
        )

    await callback.answer()


@dp.callback_query(F.data == "back_to_bank")
async def back_to_bank(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bank)
    await callback.message.edit_text(
        "<b>Оценка для банка</b>\n\nВ какой банк будет предоставляться оценка?",
        reply_markup=get_banks_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("bank_"))
async def select_bank(callback: CallbackQuery, state: FSMContext):
    bank = callback.data.split("_")[1]
    await state.update_data(bank_code=bank, bank_name=BANK_NAMES.get(bank, 'Другой'))
    await state.set_state(Form.waiting_for_mortgage_purpose)
    await callback.message.edit_text(
        f"Банк: {BANK_NAMES.get(bank)}\n\n<b>Цель оценки</b>",
        reply_markup=get_mortgage_purpose_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_mpurpose")
async def back_to_mpurpose(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.waiting_for_mortgage_purpose)
    await callback.message.edit_text(
        f"Банк: {data.get('bank_name', '')}\n\n<b>Цель оценки</b>",
        reply_markup=get_mortgage_purpose_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("mpurpose_"))
async def select_mortgage_purpose(callback: CallbackQuery, state: FSMContext):
    mp = callback.data.split("_")[1]
    names = {
        'new': 'Оформление ипотеки',
        'zaklad': 'Оформление закладной после сдачи объекта в эксплуатацию',
        'refi': 'Рефинансирование'
    }
    await state.update_data(mpurpose_code=mp, mpurpose_name=names.get(mp, ''))
    await state.set_state(Form.waiting_for_object_type)
    await callback.message.edit_text(
        f"Цель: {names.get(mp)}\n\n<b>Выберите объект оценки</b>",
        reply_markup=get_object_types_menu("back_to_mpurpose"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_report")
async def back_to_report(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.waiting_for_report_type)
    await callback.message.edit_text(
        f"<b>{data.get('purpose_name', '')}</b>\n\nВ какой форме требуется оценка?",
        reply_markup=get_report_type_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("report_"))
async def select_report_type(callback: CallbackQuery, state: FSMContext):
    rtype = callback.data.split("_")[1]
    names = {'short': 'Краткая справка', 'full': 'Отчёт об оценке'}
    await state.update_data(report_code=rtype, report_name=names.get(rtype, ''))
    await state.set_state(Form.waiting_for_object_type)
    await callback.message.edit_text(
        f"Форма: {names.get(rtype)}\n\n<b>Объект оценки</b>",
        reply_markup=get_object_types_menu("back_to_report"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("obj_"))
async def select_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    await state.update_data(object_code=obj, object_name=OBJECT_NAMES.get(obj, ''))
    
    data = await state.get_data()
    report_code = data.get('report_code')
    
    # Для краткой справки сразу показываем стоимость без адреса
    if report_code == 'short':
        if obj in ['flat', 'land', 'garage', 'parking']:
            cost = 1000
        else:
            cost = 1500
        await state.update_data(cost=cost)
        
        text = f"Объект: {OBJECT_NAMES.get(obj)}\n\n"
        text += f"Стоимость справки составит — <b>{cost} рублей</b>.\n"
        text += "Готовность в течение рабочего дня.\n\n"
        text += "Прикрепите документы на объект к заявке или отправьте на почту 7511327@mail.ru\n\n"
        text += "<b>Необходимые документы:</b>\n"
        text += "1. Выписка из ЕГРН\n"
        text += "2. Паспорт заказчика (страница 3-4 и прописка)"
        
        await state.update_data(documents=[])
        await state.set_state(Form.waiting_for_documents)
        await callback.message.edit_text(text, reply_markup=get_documents_menu("back_to_report"), parse_mode="HTML")
    else:
        await state.set_state(Form.waiting_for_address)
        await callback.message.edit_text(
            f"Объект: {OBJECT_NAMES.get(obj)}\n\n<b>{get_address_hint()}</b>",
            reply_markup=get_back_and_main_buttons("back_to_report" if not data.get('bank_code') else "back_to_mpurpose"), parse_mode="HTML"
        )
    await callback.answer()


# ========== ЗАТОПЛЕНИЕ ==========

@dp.callback_query(F.data.startswith("flood_"))
async def select_flood_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    names = {'flat': 'Квартира, комната', 'house': 'Жилой дом/садовый дом/таунхаус', 'commercial': 'Нежилое помещение'}
    await state.update_data(object_code=obj, object_name=names.get(obj, ''))
    await state.set_state(Form.waiting_for_flood_rooms)
    await callback.message.edit_text(
        f"Объект: {names.get(obj)}\n\n"
        "<b>Какое кол-во отдельных помещений объекта пострадало?</b>\n"
        "(отдельные помещения: коридор, комната, санузел, гардеробная, балкон и т.д.)\n\n"
        "Введите число:",
        reply_markup=get_back_and_main_buttons("back_to_flood_object"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_flood_object")
async def back_to_flood_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_flood_object)
    await callback.message.edit_text(
        "<b>Оценка ущерба после затопления</b>\n\nКакой объект пострадал?",
        reply_markup=get_flood_objects_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.message(Form.waiting_for_flood_rooms)
async def process_flood_rooms(message: Message, state: FSMContext):
    try:
        rooms = int(message.text.strip())
        if rooms < 1:
            await message.answer("Введите число больше 0")
            return
        await state.update_data(rooms=rooms)
        await state.set_state(Form.waiting_for_address)
        await message.answer(
            f"Помещений: {rooms}\n\n<b>{get_address_hint()}</b>",
            reply_markup=get_back_and_main_buttons("back_to_flood_rooms"), parse_mode="HTML"
        )
    except ValueError:
        await message.answer("Введите число")


@dp.callback_query(F.data == "back_to_flood_rooms")
async def back_to_flood_rooms(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.waiting_for_flood_rooms)
    await callback.message.edit_text(
        f"Объект: {data.get('object_name', '')}\n\n"
        "<b>Какое кол-во отдельных помещений объекта пострадало?</b>\n"
        "(отдельные помещения: коридор, комната, санузел, гардеробная, балкон и т.д.)\n\n"
        "Введите число:",
        reply_markup=get_back_and_main_buttons("back_to_flood_object"), parse_mode="HTML"
    )
    await callback.answer()


# ✅ ИСПРАВЛЕНО БАГ #1: Добавлен обработчик "Назад" для затопления (от даты к адресу)
@dp.callback_query(F.data == "back_to_flood_date")
async def back_to_flood_date(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Объект: {data.get('object_name', '')}\n"
        f"Помещений: {data.get('rooms', 1)}\n\n"
        f"<b>{get_address_hint()}</b>",
        reply_markup=get_back_and_main_buttons("back_to_flood_rooms"), parse_mode="HTML"
    )
    await callback.answer()


# ========== БТИ / КАДАСТР / МЕЖЕВАНИЕ ==========

@dp.callback_query(F.data == "back_to_bti")
async def back_to_bti(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_service)
    await callback.message.edit_text(
        "<b>БТИ / Кадастр / Межевание</b>\n\n👇 Выберите услугу:",
        reply_markup=get_bti_menu(), parse_mode="HTML"
    )
    await callback.answer()


# ✅ ИСПРАВЛЕНО БАГ #2: Специфичные обработчики БТИ ПЕРЕД общим
# Технический паспорт - специфичные обработчики
@dp.callback_query(F.data == "bti_passport_price")
async def bti_passport_price(callback: CallbackQuery, state: FSMContext):
    await send_price_image(callback, '(Прайс тех.паспорт).JPG')
    await callback.answer()


@dp.callback_query(F.data == "bti_passport_address")
async def bti_passport_address(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        "<b>Технический паспорт</b>\n\n" + get_address_hint(),
        reply_markup=get_back_and_main_buttons("back_to_bti_passport"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_passport")
async def back_to_bti_passport(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_passport_action)
    await callback.message.edit_text(
        "<b>Технический паспорт</b>",
        reply_markup=get_bti_passport_action_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Технический план - специфичные обработчики
@dp.callback_query(F.data == "bti_plan_price")
async def bti_plan_price(callback: CallbackQuery, state: FSMContext):
    await send_price_image(callback, '(Прайс тех.план).JPG')
    await callback.answer()


@dp.callback_query(F.data == "bti_plan_object")
async def bti_plan_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_plan_object)
    await callback.message.edit_text(
        "<b>Технический план</b>\n\nВыберите объект:",
        reply_markup=get_bti_plan_objects_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_plan")
async def back_to_bti_plan(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_plan_action)
    await callback.message.edit_text(
        "<b>Технический план</b>",
        reply_markup=get_bti_plan_action_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("btiplan_"))
async def select_bti_plan_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    names = {
        'flat': 'Квартира, комната', 'house': 'Жилой дом/садовый дом/таунхаус',
        'commercial': 'Нежилое помещение (встроенное)', 'building': 'Нежилое здание',
        'garage': 'Гараж', 'split_house': 'Раздел дома',
        'split_rooms': 'Раздел/объединение помещений'
    }
    await state.update_data(bti_object_code=obj, bti_object_name=names.get(obj, ''))
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Объект: {names.get(obj)}\n\n<b>{get_address_hint()}</b>\n\n"
        "или Кадастровый номер объекта или земельного участка на котором расположен объект",
        reply_markup=get_back_and_main_buttons("back_to_bti_plan_object"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_plan_object")
async def back_to_bti_plan_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_plan_object)
    await callback.message.edit_text(
        "<b>Технический план</b>\n\nВыберите объект:",
        reply_markup=get_bti_plan_objects_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Межевание - специфичные обработчики
@dp.callback_query(F.data == "bti_survey_price")
async def bti_survey_price(callback: CallbackQuery, state: FSMContext):
    await send_price_image(callback, '(Прайс межевание).JPG')
    await callback.answer()


@dp.callback_query(F.data == "bti_survey_service")
async def bti_survey_service(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_survey_service)
    await callback.message.edit_text(
        "<b>Межевание (земля)</b>\n\nВыберите услугу:",
        reply_markup=get_survey_services_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_survey")
async def back_to_bti_survey(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_survey_action)
    await callback.message.edit_text(
        "<b>Межевание (земля)</b>",
        reply_markup=get_bti_survey_action_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("surv_"))
async def select_survey_service(callback: CallbackQuery, state: FSMContext):
    srv = callback.data.split("_")[1]
    names = {
        'borders': 'Уточнение границ зем. участка', 'split': 'Раздел/объединение участка',
        'kuizo': 'Схема для КУиЗО', 'redistr': 'Перераспределение (межевой)',
        'redistr_full': 'Перераспределение (схема + межевой)', 'garage': 'Схема под гараж',
        'order': 'Межевой по распоряжению', 'court': 'Межевой для суда',
        'servitude': 'Межевой на сервитут', 'other': 'Другое'
    }
    await state.update_data(survey_service=srv, survey_service_name=names.get(srv, ''))
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Услуга: {names.get(srv)}\n\n"
        "<b>Введите кадастровый номер земельного участка</b>\n"
        "(например: 74:27:080301:1234)",
        reply_markup=get_back_and_main_buttons("back_to_bti_survey_service"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_survey_service")
async def back_to_bti_survey_service(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_survey_service)
    await callback.message.edit_text(
        "<b>Межевание (земля)</b>\n\nВыберите услугу:",
        reply_markup=get_survey_services_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Акты, справки - специфичные обработчики
@dp.callback_query(F.data == "bti_acts_price")
async def bti_acts_price(callback: CallbackQuery, state: FSMContext):
    await send_price_image(callback, '(Прайс Акты, справки).JPG')
    await callback.answer()


@dp.callback_query(F.data == "bti_acts_service")
async def bti_acts_service(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_acts_service)
    await callback.message.edit_text(
        "<b>Акты, справки</b>\n\nВыберите услугу:",
        reply_markup=get_acts_services_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_bti_acts")
async def back_to_bti_acts(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_bti_acts_action)
    await callback.message.edit_text(
        "<b>Акты, справки</b>",
        reply_markup=get_bti_acts_action_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("acts_"))
async def select_acts_service(callback: CallbackQuery, state: FSMContext):
    srv = callback.data.split("_")[1]
    names = {
        'input': 'Документы на акт ввода до 1500 кв.м', 'garage': 'На гараж',
        'demolish': 'Акт сноса', 'location': 'Справка о местоположении (комната)',
        'cost': 'Справка о стоимости', 'notify': 'Заполнение уведомлений (снос, перепланировка и т.д.)',
        'other': 'Другое'
    }
    await state.update_data(acts_service=srv, acts_service_name=names.get(srv, ''))

    # Сразу отправляем заявку
    data = await state.get_data()
    data['bti_service_name'] = f"Акты/справки: {names.get(srv)}"
    order_text = await format_order_text(data)
    await send_to_admins(order_text, get_user_info(callback.from_user))

    await callback.message.edit_text(
        f"✓ <b>Ваша заявка принята!</b>\n\n"
        f"Услуга: {names.get(srv)}\n\n"
        "Наш специалист свяжется с вами в ближайшее время.\n\n"
        "В рабочие дни с 9:00 до 18:00 заявки обрабатываются до 30 мин.\n"
        "В нерабочее время и выходные — на следующий рабочий день.",
        reply_markup=get_main_menu_button(), parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()


# Общий обработчик БТИ (теперь ПОСЛЕ всех специфичных)
@dp.callback_query(F.data.startswith("bti_"))
async def select_bti_service(callback: CallbackQuery, state: FSMContext):
    bti = callback.data.split("_")[1]
    
    if bti == 'extract':
        await state.update_data(bti_service='extract', bti_service_name='Выписка из технического паспорта (архивная до 2014г.)')
        await state.set_state(Form.waiting_for_address)
        await callback.message.edit_text(
            "<b>Выписка из технического паспорта (архивная до 2014г.)</b>\n\n" + get_address_hint(),
            reply_markup=get_back_and_main_buttons("back_to_bti"), parse_mode="HTML"
        )
    elif bti == 'passport':
        await state.update_data(bti_service='passport', bti_service_name='Технический паспорт')
        await state.set_state(Form.waiting_for_bti_passport_action)
        await callback.message.edit_text(
            "<b>Технический паспорт</b>",
            reply_markup=get_bti_passport_action_menu(), parse_mode="HTML"
        )
    elif bti == 'plan':
        await state.update_data(bti_service='plan', bti_service_name='Технический план')
        await state.set_state(Form.waiting_for_bti_plan_action)
        await callback.message.edit_text(
            "<b>Технический план</b>",
            reply_markup=get_bti_plan_action_menu(), parse_mode="HTML"
        )
    elif bti == 'survey':
        await state.update_data(bti_service='survey', bti_service_name='Межевание (земля)')
        await state.set_state(Form.waiting_for_bti_survey_action)
        await callback.message.edit_text(
            "<b>Межевание (земля)</b>",
            reply_markup=get_bti_survey_action_menu(), parse_mode="HTML"
        )
    elif bti == 'acts':
        await state.update_data(bti_service='acts', bti_service_name='Акты, справки')
        await state.set_state(Form.waiting_for_bti_acts_action)
        await callback.message.edit_text(
            "<b>Акты, справки</b>",
            reply_markup=get_bti_acts_action_menu(), parse_mode="HTML"
        )
    
    await callback.answer()


# ========== ЭКСПЕРТИЗА / ОБСЛЕДОВАНИЯ ==========

@dp.callback_query(F.data == "back_to_expertise")
async def back_to_expertise(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_type)
    await callback.message.edit_text(
        "<b>Строительно-техническая экспертиза / Обследования</b>\n\n👇 Выберите тип услуги:",
        reply_markup=get_expertise_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("exp_"))
async def select_expertise_type(callback: CallbackQuery, state: FSMContext):
    exp = callback.data.split("_")[1]
    names = {
        'build': 'Строительно-техническая экспертиза',
        'accept': 'Приемка жилого дома от застройщика',
        'inspect': 'Техническое обследование жилого дома перед покупкой',
        'thermal': 'Тепловизионное обследование'
    }
    await state.update_data(exp_type=exp, exp_type_name=names.get(exp, ''))

    if exp == 'build':
        await state.set_state(Form.waiting_for_expertise_stage)
        await callback.message.edit_text(
            "<b>Строительно-техническая экспертиза</b>\n\n"
            "Здравствуйте!\n\n"
            "Я помогу оформить заявку на строительно-техническую экспертизу.\n"
            "Ответьте, пожалуйста, на несколько вопросов — это займёт меньше минуты.\n\n"
            "<b>На каком этапе сейчас находится ваш спор или ситуация?</b>",
            reply_markup=get_expertise_stage_menu(), parse_mode="HTML"
        )

    elif exp == 'accept':
        await state.set_state(Form.waiting_for_acceptance_finish)
        await callback.message.edit_text(
            "<b>Приемка жилого дома от застройщика</b>\n\n"
            "Здравствуйте!\n\n"
            "Я помогу оформить заявку на приёмку жилого дома от застройщика.\n"
            "Это займёт меньше минуты — ответьте, пожалуйста, на несколько вопросов.\n\n"
            "<b>Какое состояние внутренней отделки жилого дома?</b>",
            reply_markup=get_acceptance_finish_menu(), parse_mode="HTML"
        )

    elif exp == 'inspect':
        await state.set_state(Form.waiting_for_inspection_area)
        await callback.message.edit_text(
            "<b>Техническое обследование жилого дома перед покупкой</b>\n\n"
            "✓ Тщательный осмотр с инструментальным обследованием фундамента, стен, перекрытий, кровли и инженерных сетей.\n\n"
            "✓ Выявление скрытых дефектов — трещины, просадки, протечки, ошибки строительства, места промерзания\n\n"
            "✓ Оценка реального состояния дома — прочность конструкций, надежность инженерных коммуникаций, прогноз долговечности.\n\n"
            "✓ Консультация и рекомендации по устранению недостатков и возможным затратам на ремонт.\n\n"
            "✓ Аргументация для торга — в 99% случаев удается снизить цену дома на 1-10% за счет выявленных недостатков\n\n"
            "<b>Используемое оборудование:</b>\n"
            "◆ Склерометр — проверка прочности бетона.\n"
            "◆ Лазерный уровень — проверка геометрии стен и перекрытий.\n"
            "◆ Влагомер — выявление скрытой сырости в стенах, фундаменте, деревянных конструкциях\n"
            "◆ Тепловизор — обнаружение теплопотерь, промерзаний и утечек тепла.\n"
            "◆ Эндоскоп — диагностика скрытых полостей в конструкциях\n"
            "◆ Тестер электропроводки — проверка наличия напряжения, выявления скрытых повреждений и ошибок подключения\n\n"
            "<b>Укажите площадь дома:</b>",
            reply_markup=get_inspection_area_menu(), parse_mode="HTML"
        )

    elif exp == 'thermal':
        await state.set_state(Form.waiting_for_thermal_object)
        await callback.message.edit_text(
            "<b>Тепловизионное обследование</b>\n\n"
            "Здравствуйте!\n\n"
            "Я помогу оформить заявку на тепловизионное обследование.\n"
            "Это займёт меньше минуты — ответьте, пожалуйста, на несколько вопросов.\n\n"
            "<b>Выберите объект:</b>",
            reply_markup=get_thermal_object_menu(), parse_mode="HTML"
        )

    await callback.answer()


# Строительная экспертиза — этап
@dp.callback_query(F.data == "back_to_exp_stage")
async def back_to_exp_stage(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_stage)
    await callback.message.edit_text(
        "<b>Строительно-техническая экспертиза</b>\n\n"
        "Здравствуйте!\n\n"
        "Я помогу оформить заявку на строительно-техническую экспертизу.\n"
        "Ответьте, пожалуйста, на несколько вопросов — это займёт меньше минуты.\n\n"
        "<b>На каком этапе сейчас находится ваш спор или ситуация?</b>",
        reply_markup=get_expertise_stage_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("expstage_"))
async def select_expertise_stage(callback: CallbackQuery, state: FSMContext):
    stage = callback.data.split("_")[1]
    names = {
        'court': 'Уже идёт судебный процесс',
        'pretrial': 'Подготовка претензии / досудебное урегулирование',
        'unknown': 'Затрудняюсь ответить'
    }
    await state.update_data(exp_stage=stage, exp_stage_name=names.get(stage, ''))
    await state.set_state(Form.waiting_for_expertise_object)
    await callback.message.edit_text(
        "<b>Какой объект требуется обследовать?</b>",
        reply_markup=get_expertise_object_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Строительная экспертиза — объект
@dp.callback_query(F.data == "back_to_exp_object")
async def back_to_exp_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_object)
    await callback.message.edit_text(
        "<b>Какой объект требуется обследовать?</b>",
        reply_markup=get_expertise_object_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("expobj_"))
async def select_expertise_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    names = {
        'flat': 'Квартира', 'house': 'Индивидуальный жилой дом / коттедж',
        'commercial': 'Помещение / офис / коммерческий объект', 'roof': 'Кровля',
        'foundation': 'Фундамент', 'other': 'Другое'
    }
    
    if obj == 'other':
        await state.update_data(exp_object='other', exp_object_name='Другое (ввести свой вариант)')
        await callback.message.edit_text(
            "Введите описание объекта:",
            reply_markup=get_back_and_main_buttons("back_to_exp_object"), parse_mode="HTML"
        )
        # Будет обработано в waiting_for_expertise_description
    else:
        await state.update_data(exp_object=obj, exp_object_name=names.get(obj, ''))
        await state.set_state(Form.waiting_for_expertise_status)
        await callback.message.edit_text(
            "<b>Объект уже построен или находится в процессе строительства?</b>",
            reply_markup=get_expertise_status_menu(), parse_mode="HTML"
        )
    await callback.answer()


# Строительная экспертиза — статус
@dp.callback_query(F.data == "back_to_exp_status")
async def back_to_exp_status(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_status)
    await callback.message.edit_text(
        "<b>Объект уже построен или находится в процессе строительства?</b>",
        reply_markup=get_expertise_status_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("expstat_"))
async def select_expertise_status(callback: CallbackQuery, state: FSMContext):
    status = callback.data.split("_")[1]
    names = {
        'built': 'Построен',
        'building': 'В процессе строительства',
        'renovated': 'После ремонта / реконструкции'
    }
    await state.update_data(exp_status=status, exp_status_name=names.get(status, ''), exp_goals=[])
    await state.set_state(Form.waiting_for_expertise_goals)
    await callback.message.edit_text(
        "<b>Что нужно определить или исследовать в рамках экспертизы?</b>\n"
        "(можно выбрать несколько вариантов, затем нажмите «Продолжить»)",
        reply_markup=get_expertise_goals_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Строительная экспертиза — цели (множественный выбор)
@dp.callback_query(F.data.startswith("expgoal_"))
async def select_expertise_goal(callback: CallbackQuery, state: FSMContext):
    goal = callback.data.split("_")[1]

    if goal == 'done':
        await state.set_state(Form.waiting_for_expertise_description)
        await callback.message.edit_text(
            "<b>Опишите, пожалуйста, коротко, какие есть проблемы или что вызывает сомнения.</b>\n\n"
            "(пример: трещины, протечки, неровная кладка, плесень, не совпадает со сметой и т.д.)",
            reply_markup=get_back_and_main_buttons("back_to_exp_goals"), parse_mode="HTML"
        )
    elif goal == 'other':
        data = await state.get_data()
        goals = data.get('exp_goals', [])
        goals.append('Другое')
        await state.update_data(exp_goals=goals)
        await callback.answer("✓ Добавлено: Другое")
        return
    else:
        data = await state.get_data()
        goals = data.get('exp_goals', [])
        goal_names = {
            'defects': 'Выявить строительные дефекты и нарушения',
            'cost': 'Рассчитать стоимость устранения дефектов',
            'volume': 'Оценить объём выполненных/невыполненных работ',
            'docs': 'Проверить соответствие нормативной документации',
            'claims': 'Подтвердить или опровергнуть претензии другой стороны',
            'complex': 'Провести комплексное обследование'
        }
        goal_name = goal_names.get(goal, goal)
        if goal_name not in goals:
            goals.append(goal_name)
            await state.update_data(exp_goals=goals)
            await callback.answer(f"✓ Добавлено: {goal_name}")
        else:
            await callback.answer(f"Уже выбрано")
        return

    await callback.answer()


@dp.callback_query(F.data == "back_to_exp_goals")
async def back_to_exp_goals(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_goals)
    await callback.message.edit_text(
        "<b>Что нужно определить или исследовать в рамках экспертизы?</b>\n"
        "(можно выбрать несколько вариантов, затем нажмите «Продолжить»)",
        reply_markup=get_expertise_goals_menu(), parse_mode="HTML"
    )
    await callback.answer()


# ✅ ИСПРАВЛЕНО БАГ #1: Добавлен обработчик "Назад" для экспертизы
@dp.callback_query(F.data == "back_to_exp_description")
async def back_to_exp_description(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_expertise_goals)
    await callback.message.edit_text(
        "<b>Что нужно определить или исследовать в рамках экспертизы?</b>\n"
        "(можно выбрать несколько вариантов, затем нажмите «Продолжить»)",
        reply_markup=get_expertise_goals_menu(), parse_mode="HTML"
    )
    await callback.answer()


# Строительная экспертиза — описание проблемы
@dp.message(Form.waiting_for_expertise_description)
async def process_expertise_description(message: Message, state: FSMContext):
    await state.update_data(exp_description=message.text, documents=[])
    await state.set_state(Form.waiting_for_expertise_photos)
    await message.answer(
        "Прикрепите, если возможно, фото или видео проблемных мест — это поможет эксперту предварительно оценить ситуацию.\n"
        "(можно отправить несколько фото подряд)\n\n"
        "Или нажмите кнопку для отправки заявки:",
        reply_markup=get_finish_docs_menu(), parse_mode="HTML"
    )


# Строительная экспертиза — фото
@dp.message(Form.waiting_for_expertise_photos, F.photo)
async def process_expertise_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    docs = data.get('documents', [])
    docs.append({'type': 'photo', 'file_id': message.photo[-1].file_id, 'caption': 'Фото к экспертизе'})
    await state.update_data(documents=docs)
    await message.answer(
        f"✓ Фото добавлено ({len(docs)} шт)\n\nДобавьте ещё или отправьте заявку:",
        reply_markup=get_finish_docs_menu()
    )


# ========== ПРИЁМКА ОТ ЗАСТРОЙЩИКА ==========

@dp.callback_query(F.data == "back_to_acc_finish")
async def back_to_acc_finish(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_acceptance_finish)
    await callback.message.edit_text(
        "<b>Приемка жилого дома от застройщика</b>\n\n"
        "Здравствуйте!\n\n"
        "Я помогу оформить заявку на приёмку жилого дома от застройщика.\n"
        "Это займёт меньше минуты — ответьте, пожалуйста, на несколько вопросов.\n\n"
        "<b>Какое состояние внутренней отделки жилого дома?</b>",
        reply_markup=get_acceptance_finish_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("accfin_"))
async def select_acceptance_finish(callback: CallbackQuery, state: FSMContext):
    fin = callback.data.split("_")[1]
    names = {'rough': 'Черновая (без отделки)', 'pre': 'Предчистовая', 'final': 'Чистовая (с отделкой)'}
    await state.update_data(acc_finish=fin, acc_finish_name=names.get(fin, ''))
    await state.set_state(Form.waiting_for_acceptance_material)
    await callback.message.edit_text(
        "<b>Какой материал стен?</b>",
        reply_markup=get_acceptance_material_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_acc_material")
async def back_to_acc_material(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_acceptance_material)
    await callback.message.edit_text(
        "<b>Какой материал стен?</b>",
        reply_markup=get_acceptance_material_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("accmat_"))
async def select_acceptance_material(callback: CallbackQuery, state: FSMContext):
    mat = callback.data.split("_")[1]
    names = {'brick': 'Кирпич', 'panel': 'Ж/б панели', 'block': 'Блочный (газоблок, пеноблок и др)', 'wood': 'Дерево', 'other': 'Другой'}
    await state.update_data(acc_material=mat, acc_material_name=names.get(mat, ''))
    await state.set_state(Form.waiting_for_acceptance_area)
    await callback.message.edit_text(
        "<b>Какая площадь объекта?</b>",
        reply_markup=get_acceptance_area_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("accarea_"))
async def select_acceptance_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_")[1]
    names = {'150': 'до 150 кв.м.', '250': '150-250 кв.м.', '500': '250-500 кв.м.'}
    await state.update_data(acc_area=area, acc_area_name=names.get(area, ''))
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Площадь: {names.get(area)}\n\n<b>{get_address_hint()}</b>",
        reply_markup=get_back_and_main_buttons("back_to_acc_area"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_acc_area")
async def back_to_acc_area(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_acceptance_area)
    await callback.message.edit_text(
        "<b>Какая площадь объекта?</b>",
        reply_markup=get_acceptance_area_menu(), parse_mode="HTML"
    )
    await callback.answer()


# ========== ОБСЛЕДОВАНИЕ ПЕРЕД ПОКУПКОЙ ==========

@dp.callback_query(F.data == "back_to_insp_area")
async def back_to_insp_area(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_inspection_area)
    await callback.message.edit_text(
        "<b>Техническое обследование жилого дома перед покупкой</b>\n\n"
        "<b>Укажите площадь дома:</b>",
        reply_markup=get_inspection_area_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("insparea_"))
async def select_inspection_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_")[1]
    names = {'150': 'до 150 кв.м.', '250': '150-250 кв.м.', '350': '250-350 кв.м.', '350plus': 'свыше 350 кв.м.'}
    await state.update_data(insp_area=area, insp_area_name=names.get(area, ''))
    await state.set_state(Form.waiting_for_inspection_material)
    await callback.message.edit_text(
        "<b>Какой материал стен дома?</b>",
        reply_markup=get_inspection_material_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_insp_material")
async def back_to_insp_material(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_inspection_material)
    await callback.message.edit_text(
        "<b>Какой материал стен дома?</b>",
        reply_markup=get_inspection_material_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("inspmat_"))
async def select_inspection_material(callback: CallbackQuery, state: FSMContext):
    mat = callback.data.split("_")[1]
    names = {'brick': 'Кирпич', 'panel': 'Ж/б панели', 'block': 'Блочный (газоблок, пеноблок и др)', 'wood': 'Дерево', 'other': 'Другой'}
    await state.update_data(insp_material=mat, insp_material_name=names.get(mat, ''))
    await state.set_state(Form.waiting_for_inspection_finish)
    await callback.message.edit_text(
        "<b>Какое состояние внутренней отделки?</b>\n\n"
        "Примечание: Объективную оценку состояния дома можно провести только на объектах без отделки или с минимальной отделкой. "
        "Обжитые дома с отделкой сложнее проверить, так как большинство дефектов скрыто за облицовочными материалами.",
        reply_markup=get_inspection_finish_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("inspfin_"))
async def select_inspection_finish(callback: CallbackQuery, state: FSMContext):
    fin = callback.data.split("_")[1]
    names = {'rough': 'Черновая (без отделки)', 'pre': 'Предчистовая (стены оштукатурены)', 'final': 'Чистовая (с отделкой)'}
    await state.update_data(insp_finish=fin, insp_finish_name=names.get(fin, ''))
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Отделка: {names.get(fin)}\n\n<b>{get_address_hint()}</b>",
        reply_markup=get_back_and_main_buttons("back_to_insp_finish"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_insp_finish")
async def back_to_insp_finish(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_inspection_finish)
    await callback.message.edit_text(
        "<b>Какое состояние внутренней отделки?</b>\n\n"
        "Примечание: Объективную оценку состояния дома можно провести только на объектах без отделки или с минимальной отделкой.",
        reply_markup=get_inspection_finish_menu(), parse_mode="HTML"
    )
    await callback.answer()


# ========== ТЕПЛОВИЗОР ==========

@dp.callback_query(F.data == "back_to_therm_object")
async def back_to_therm_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_thermal_object)
    await callback.message.edit_text(
        "<b>Тепловизионное обследование</b>\n\n"
        "Здравствуйте!\n\n"
        "Я помогу оформить заявку на тепловизионное обследование.\n"
        "Это займёт меньше минуты — ответьте, пожалуйста, на несколько вопросов.\n\n"
        "<b>Выберите объект:</b>",
        reply_markup=get_thermal_object_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("thermobj_"))
async def select_thermal_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    names = {'flat': 'Квартира', 'house': 'Жилой дом'}
    await state.update_data(therm_object=obj, therm_object_name=names.get(obj, ''))
    await state.set_state(Form.waiting_for_thermal_area)
    await callback.message.edit_text(
        "<b>Укажите площадь:</b>",
        reply_markup=get_thermal_area_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("thermarea_"))
async def select_thermal_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_")[1]
    names = {'100': 'до 100 кв.м.', '200': '100-200 кв.м.', '300': '200-300 кв.м.', '300plus': 'свыше 300 кв.м.'}
    await state.update_data(therm_area=area, therm_area_name=names.get(area, ''))
    await state.set_state(Form.waiting_for_address)
    await callback.message.edit_text(
        f"Площадь: {names.get(area)}\n\n<b>{get_address_hint()}</b>",
        reply_markup=get_back_and_main_buttons("back_to_therm_area"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_therm_area")
async def back_to_therm_area(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_thermal_area)
    await callback.message.edit_text(
        "<b>Укажите площадь:</b>",
        reply_markup=get_thermal_area_menu(), parse_mode="HTML"
    )
    await callback.answer()


# ========== СТРАХОВАНИЕ ==========

@dp.callback_query(F.data == "back_to_ins_type")
async def back_to_ins_type(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_insurance_type)
    await callback.message.edit_text(
        "<b>Ипотечное страхование</b>\n\n👇 Выберите тип:",
        reply_markup=get_insurance_type_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("ins_"))
async def select_insurance_type(callback: CallbackQuery, state: FSMContext):
    ins = callback.data.split("_")[1]
    names = {'new': 'Новая ипотека', 'renew': 'Продление действующего договора страхования'}
    await state.update_data(ins_type=ins, ins_type_name=names.get(ins, ''))
    await state.set_state(Form.waiting_for_insurance_coverage)
    await callback.message.edit_text(
        f"Тип: {names.get(ins)}\n\n<b>Выберите, что вы хотите застраховать:</b>",
        reply_markup=get_insurance_coverage_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_ins_coverage")
async def back_to_ins_coverage(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.waiting_for_insurance_coverage)
    await callback.message.edit_text(
        f"Тип: {data.get('ins_type_name', '')}\n\n<b>Выберите, что вы хотите застраховать:</b>",
        reply_markup=get_insurance_coverage_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("inscov_"))
async def select_insurance_coverage(callback: CallbackQuery, state: FSMContext):
    cov = callback.data.split("_")[1]
    names = {'property': 'Недвижимость (конструктив)', 'life': 'Жизнь', 'both': 'Недвижимость + Жизнь'}
    await state.update_data(ins_coverage=cov, ins_coverage_name=names.get(cov, ''))
    await state.set_state(Form.waiting_for_insurance_object)
    await callback.message.edit_text(
        "<b>Объект страхования:</b>",
        reply_markup=get_insurance_object_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("insobj_"))
async def select_insurance_object(callback: CallbackQuery, state: FSMContext):
    obj = callback.data.split("_")[1]
    names = {'flat': 'Квартира, комната', 'house': 'Жилой дом/садовый дом/таунхаус'}
    await state.update_data(ins_object=obj, ins_object_name=names.get(obj, ''))
    await state.set_state(Form.waiting_for_mortgage_balance)
    await callback.message.edit_text(
        "<b>Введите, пожалуйста, остаток по ипотеке на сегодня (в рублях)</b>",
        reply_markup=get_back_and_main_buttons("back_to_ins_object"), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_ins_object")
async def back_to_ins_object(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_insurance_object)
    await callback.message.edit_text(
        "<b>Объект страхования:</b>",
        reply_markup=get_insurance_object_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.message(Form.waiting_for_mortgage_balance)
async def process_mortgage_balance(message: Message, state: FSMContext):
    try:
        balance = float(message.text.replace(' ', '').replace(',', '.'))
        if balance <= 0:
            await message.answer("Введите положительное число")
            return

        data = await state.get_data()
        cost = calculate_insurance_cost(data.get('ins_object', 'flat'), balance)
        await state.update_data(balance=balance, cost=cost, documents=[])

        ins_type = data.get('ins_type', 'new')
        ins_coverage = data.get('ins_coverage', 'property')

        text = f"<b>Предварительный расчет стоимости полиса</b>\n\n"
        text += f"Остаток по ипотеке: {int(balance):,} ₽\n".replace(',', ' ')
        text += f"Стоимость полиса составит: <b>{cost} рублей</b>\n\n"
        text += "Это предварительный расчёт. Для точного расчёта стоимости полиса прикрепите, пожалуйста, необходимые документы.\n\n"

        text += "<b>Необходимый перечень документов для точного расчета стоимости полиса:</b>\n\n"
        
        if ins_type == 'new':
            text += "◆ Паспорт (страницы: фото и прописка)\n"
            text += "◆ Выписка ЕГРН\n"
            text += "◆ Отчёт об оценке\n"
            text += "◆ Кредитный договор\n"
        else:  # renew
            text += "◆ Предыдущий страховой договор\n"
            text += "◆ Действующий кредитный договор\n"

        if ins_coverage in ['life', 'both']:
            text += "\n<b>Для страхования жизни укажите:</b>\n"
            text += "◆ Ваша профессия\n"
            text += "◆ Состояние здоровья (варианты: Без отклонений / Незначительные отклонения / Значительные отклонения)\n"
            text += "◆ Занимаетесь ли профессиональным спортом (Да / Нет)\n"
            await state.set_state(Form.waiting_for_insurance_life_info)
            await state.update_data(need_life_info=True)
        else:
            await state.set_state(Form.waiting_for_insurance_documents)

        text += f"\n\nИли отправьте документы на почту: 7511327@mail.ru"

        await message.answer(text, reply_markup=get_documents_menu("back_to_ins_object"), parse_mode="HTML")
    except ValueError:
        await message.answer("Введите число\n\nПример: 2500000")


@dp.message(Form.waiting_for_insurance_life_info)
async def process_insurance_life_info(message: Message, state: FSMContext):
    await state.update_data(life_info=message.text)
    await state.set_state(Form.waiting_for_insurance_documents)
    await message.answer(
        "✓ Информация сохранена\n\n"
        "Пожалуйста, прикрепите указанные документы одним или несколькими файлами:",
        reply_markup=get_documents_menu("back_to_ins_object"), parse_mode="HTML"
    )


# ========== СДЕЛКИ ==========

@dp.callback_query(F.data.startswith("deals_"))
async def select_deals_service(callback: CallbackQuery, state: FSMContext):
    srv = callback.data.split("_")[1]

    if srv == 'egrn':
        text = "<b>Выписки из ЕГРН</b>\n\nПерейдите в бот:\n👉 @EGRN_365bot"
    else:
        text = "<b>Анализ сделок за квартал</b>\n\nПерейдите в бот:\n👉 @realestate_deals_bot"

    await send_to_admins(
        f"◆ <b>Сделки с недвижимостью</b>\n\nЗапрос: {'Выписки ЕГРН' if srv == 'egrn' else 'Анализ сделок'}",
        get_user_info(callback.from_user)
    )

    await callback.message.edit_text(text, reply_markup=get_main_menu_button(), parse_mode="HTML")
    await state.clear()
    await callback.answer()


# ========== ОБРАБОТКА АДРЕСА ==========

@dp.message(Form.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    address = message.text.strip()
    await state.update_data(address=address)

    processing = await message.answer("Определяем местоположение...")

    lat, lon, full_address = await geocode_address(address)

    if lat:
        distance = round(calculate_distance(CHELYABINSK_CENTER[0], CHELYABINSK_CENTER[1], lat, lon), 1)
        in_city = is_in_chelyabinsk(full_address)
        await state.update_data(full_address=full_address, distance=distance, in_city=in_city)
    else:
        distance = 0
        in_city = True
        full_address = address
        await state.update_data(distance=0, in_city=True)

    await processing.delete()

    data = await state.get_data()
    service = data.get('service_type', '')

    if service == 'evaluation':
        if data.get('bank_code'):
            base, travel, total = calculate_mortgage_cost(
                data['bank_code'], data.get('object_code', 'flat'),
                data.get('mpurpose_code', 'new'), distance, in_city
            )
        else:
            base, travel, total = calculate_other_cost(
                data.get('object_code', 'flat'), data.get('report_code', 'full'), distance, in_city
            )
        await state.update_data(cost=total)

        text = f"Распознанный адрес: {full_address}\n"
        text += f"Расстояние от центра: {distance} км\n\n"
        text += f"Стоимость с учетом выезда на объект составит: <b>{total} ₽</b>\n\n"
        text += "Срок готовности 1-2 дня после выезда на объект и предоставления всех необходимых документов для оценки.\n"
        text += "Доплата за площадь объекта свыше 150 кв.м — 1000 руб за каждые 150 кв.м.\n"
        text += "Коэффициент за срочность подготовки отчета об оценке (в день осмотра) — 1,3\n\n"
        text += "<b>Введите желаемую дату и время осмотра:</b>"

        await state.set_state(Form.waiting_for_date)
        await message.answer(text, reply_markup=get_back_and_main_buttons(), parse_mode="HTML")

    elif service == 'flood':
        rooms = data.get('rooms', 1)
        base, rooms_cost, travel, total = calculate_flood_cost(
            data.get('object_code', 'flat'), rooms, distance, in_city
        )
        await state.update_data(cost=total)

        text = f"Распознанный адрес: {full_address}\n"
        text += f"Расстояние от центра: {distance} км\n\n"
        text += f"Стоимость отчета об оценке с учетом выезда на объект составит: <b>{total} ₽</b>\n\n"
        text += "Срок готовности 3-5 дня после выезда на объект\n\n"
        text += "<b>Введите желаемую дату и время осмотра:</b>"

        await state.set_state(Form.waiting_for_date)
        await message.answer(text, reply_markup=get_back_and_main_buttons("back_to_flood_date"), parse_mode="HTML")

    elif service == 'bti':
        bti_service = data.get('bti_service', '')

        if bti_service == 'extract':
            await state.update_data(cost=500)
            order_text = await format_order_text(await state.get_data())
            await send_to_admins(order_text, get_user_info(message.from_user))

            await message.answer(
                "✓ <b>Ваша заявка принята!</b>\n\n"
                "При наличии выписки из тех.паспорта её стоимость составит — <b>500 руб.</b>\n"
                "Готовность в течение дня.\n\n"
                "Наш специалист свяжется с вами в ближайшее время.\n\n"
                "В рабочие дни с 9:00 до 18:00 заявки обрабатываются до 30 мин.\n"
                "В нерабочее время и выходные — на следующий рабочий день.",
                reply_markup=get_main_menu_button(), parse_mode="HTML"
            )
            await state.clear()
        else:
            order_text = await format_order_text(data)
            await send_to_admins(order_text, get_user_info(message.from_user))

            await message.answer(
                "✓ <b>Ваша заявка принята!</b>\n\n"
                "Наш специалист свяжется с вами в ближайшее время.\n\n"
                "В рабочие дни с 9:00 до 18:00 заявки обрабатываются до 30 мин.\n"
                "В нерабочее время и выходные — на следующий рабочий день.",
                reply_markup=get_main_menu_button(), parse_mode="HTML"
            )
            await state.clear()

    elif service == 'expertise':
        exp_type = data.get('exp_type', '')

        if exp_type == 'accept':
            base, travel, total = calculate_acceptance_cost(data.get('acc_area', '150'), distance, in_city)
        elif exp_type == 'inspect':
            base, travel, total = calculate_inspection_cost(data.get('insp_area', '150'), distance, in_city)
        elif exp_type == 'thermal':
            base, travel, total = calculate_thermal_cost(
                data.get('therm_object', 'flat'), data.get('therm_area', '100'), distance, in_city
            )
        else:
            total = 0

        await state.update_data(cost=total)

        if total > 0:
            text = f"Распознанный адрес: {full_address}\n"
            text += f"Расстояние от центра: {distance} км\n\n"
            text += f"Стоимость с учетом выезда на объект составит: <b>{total} ₽</b>\n\n"
            text += "<b>Введите желаемую дату и время осмотра:</b>"

            await state.set_state(Form.waiting_for_date)
            await message.answer(text, reply_markup=get_back_and_main_buttons(), parse_mode="HTML")
        else:
            await state.update_data(documents=[])
            await state.set_state(Form.waiting_for_documents)
            await message.answer(
                "Прикрепите документы или отправьте заявку:",
                reply_markup=get_documents_menu(), parse_mode="HTML"
            )


# ========== ДАТА ==========

@dp.message(Form.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    date = message.text.strip()
    await state.update_data(date=date, documents=[])
    await state.set_state(Form.waiting_for_documents)

    data = await state.get_data()
    service = data.get('service_type', '')
    mpurpose = data.get('mpurpose_code', '')

    text = f"Дата и время: {date}\n\n"
    text += "Прикрепите документы на объект к заявке или отправьте на почту 7511327@mail.ru\n\n"
    text += "<b>Необходимые документы:</b>\n"

    if service == 'evaluation' and data.get('bank_code'):
        if mpurpose in ['new', 'refi']:
            text += "1. Выписка из ЕГРН\n"
            text += "2. Технический паспорт/выписка из техпаспорта/технический план\n"
            text += "3. Паспорт(а) собственника(ов) и паспорт заемщика (страница 3-4 и прописка)"
        else:  # zaklad
            text += "<b>Для квартиры:</b>\n"
            text += "1. Договор долевого участия/договор уступки/договор купли-продажи\n"
            text += "2. Акт приема-передачи\n"
            text += "3. Паспорт заемщика (страница 3-4 и прописка)\n\n"
            text += "<b>Для жилого дома:</b>\n"
            text += "1. Выписка из ЕГРН на жилой дом и земельный участок\n"
            text += "2. Технический план\n"
            text += "3. Паспорт заемщика (страница 3-4 и прописка)"
    elif service == 'flood':
        text += "1. Выписка из ЕГРН\n"
        text += "2. Паспорт заказчика (страница 3-4 и прописка)\n"
        text += "3. Акт от управляющей компании\n"
        text += "4. Технический паспорт (при наличии)"
    else:
        text += "1. Выписка из ЕГРН\n"
        text += "2. Паспорт заказчика (страница 3-4 и прописка)"

    await message.answer(text, reply_markup=get_documents_menu(), parse_mode="HTML")


# ========== ДОКУМЕНТЫ ==========

@dp.callback_query(F.data == "attach_docs")
async def start_attach_docs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "<b>Прикрепление документов</b>\n\n"
        "Отправьте фото или файлы.\n"
        "После загрузки всех документов нажмите «Готово»",
        reply_markup=get_finish_docs_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "add_more_docs")
async def add_more_docs(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отправьте ещё документы\n\nИли нажмите «Готово» для отправки заявки",
        reply_markup=get_finish_docs_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.message(Form.waiting_for_documents, F.photo)
async def handle_doc_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    docs = data.get('documents', [])
    docs.append({'type': 'photo', 'file_id': message.photo[-1].file_id, 'caption': ''})
    await state.update_data(documents=docs)
    await message.answer(
        f"✓ Фото добавлено ({len(docs)} файлов)\n\nДобавьте ещё или нажмите «Готово»",
        reply_markup=get_finish_docs_menu()
    )


@dp.message(Form.waiting_for_documents, F.document)
async def handle_doc_file(message: Message, state: FSMContext):
    data = await state.get_data()
    docs = data.get('documents', [])
    docs.append({'type': 'document', 'file_id': message.document.file_id, 'caption': message.document.file_name or ''})
    await state.update_data(documents=docs)
    await message.answer(
        f"✓ Файл добавлен ({len(docs)} файлов)\n\nДобавьте ещё или нажмите «Готово»",
        reply_markup=get_finish_docs_menu()
    )


@dp.message(Form.waiting_for_insurance_documents, F.photo)
async def handle_ins_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    docs = data.get('documents', [])
    docs.append({'type': 'photo', 'file_id': message.photo[-1].file_id, 'caption': ''})
    await state.update_data(documents=docs)
    await message.answer(
        f"✓ Фото добавлено ({len(docs)})\n\nДобавьте ещё или отправьте заявку",
        reply_markup=get_finish_docs_menu()
    )


@dp.message(Form.waiting_for_insurance_documents, F.document)
async def handle_ins_file(message: Message, state: FSMContext):
    data = await state.get_data()
    docs = data.get('documents', [])
    docs.append({'type': 'document', 'file_id': message.document.file_id, 'caption': message.document.file_name or ''})
    await state.update_data(documents=docs)
    await message.answer(
        f"✓ Файл добавлен ({len(docs)})\n\nДобавьте ещё или отправьте заявку",
        reply_markup=get_finish_docs_menu()
    )


# ========== ОТПРАВКА ЗАЯВКИ ==========

@dp.callback_query(F.data == "submit_order")
async def submit_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_info = get_user_info(callback.from_user)
    order_text = await format_order_text(data)

    await send_to_admins(order_text, user_info)

    docs = data.get('documents', [])
    if docs:
        await send_documents_to_admins(docs, user_info, order_text)

    cost_info = f"\nСтоимость: {data.get('cost')} ₽" if data.get('cost') else ""

    await callback.message.edit_text(
        f"✓ <b>Ваша заявка принята!</b>{cost_info}\n\n"
        f"Документов: {len(docs)}\n\n"
        "Наш специалист свяжется с вами в ближайшее время.\n\n"
        "В рабочие дни с 9:00 до 18:00 заявки обрабатываются до 30 мин.\n"
        "В нерабочее время и выходные — на следующий рабочий день.",
        reply_markup=get_main_menu_button(), parse_mode="HTML"
    )
    await state.clear()
    await callback.answer("✓ Заявка отправлена!")


# ========== ЗАПУСК ==========

async def main():
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
