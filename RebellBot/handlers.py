from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services import TradingEngine
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()
trading_engine = TradingEngine()


class UserState(StatesGroup):
    AWAIT_TICKER = State()
    AWAIT_MODE = State()


def main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с кнопками"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Анализ инструмента")],
            [KeyboardButton(text="📈 Топовые инструменты")],
            [KeyboardButton(text="🔄 Сменить режим")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )


def mode_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора режима"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Краткосрочный (1 час)")],
            [KeyboardButton(text="Долгосрочный (1 день)")]
        ],
        resize_keyboard=True
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🤖 Добро пожаловать в торгового бота!\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=main_keyboard()
    )


@router.message(F.text == "📊 Анализ инструмента")
async def analyze_instrument(message: Message, state: FSMContext):
    await state.set_state(UserState.AWAIT_TICKER)
    await message.answer(
        "Введите тикер инструмента (например: SBER):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Назад")]],
            resize_keyboard=True
        )
    )


@router.message(F.text == "📈 Топовые инструменты")
async def top_instruments(message: Message):
    try:
        instruments = await trading_engine.get_top_instruments()
        response = "📈 Топ-5 инструментов:\n" + "\n".join(
            f"{idx + 1}. {item['ticker']} ({item['name']})"
            for idx, item in enumerate(instruments)
        )
        await message.answer(response, reply_markup=main_keyboard())
    except Exception as e:
        logger.error(str(e))
        await message.answer("⚠️ Ошибка получения данных", reply_markup=main_keyboard())


@router.message(F.text == "🔄 Сменить режим")
async def change_mode(message: Message, state: FSMContext):
    await state.set_state(UserState.AWAIT_MODE)
    await message.answer(
        "Выберите режим анализа:",
        reply_markup=mode_keyboard()
    )


@router.message(UserState.AWAIT_MODE, F.text.in_(["Краткосрочный (1 час)", "Долгосрочный (1 день)"]))
async def process_mode(message: Message, state: FSMContext):
    mode = "short_term" if "Краткосрочный" in message.text else "long_term"
    await state.update_data(mode=mode)
    await message.answer(
        f"✅ Режим изменён на: {message.text}",
        reply_markup=main_keyboard()
    )
    await state.clear()


@router.message(UserState.AWAIT_TICKER)
async def process_ticker(message: Message, state: FSMContext):
    if message.text == "↩️ Назад":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_keyboard())
        return

    user_data = await state.get_data()
    mode = user_data.get("mode", "short_term")

    try:
        analysis = await trading_engine.analyze(
            ticker=message.text.upper(),
            mode=mode
        )

        response = (
            f"📊 Анализ {message.text.upper()} ({'Краткосрочный' if mode == 'short_term' else 'Долгосрочный'}):\n"
            f"• Рекомендация: {analysis['decision']}\n"
            f"• Уверенность: {analysis['confidence']}%\n"
            f"• Цена: {analysis['price']:.2f} RUB\n"
            f"• Стоп-лосс: {analysis['stop_loss']:.2f}\n"
            f"• Тейк-профит: {analysis['take_profit']:.2f}"
        )

        await message.answer(response, reply_markup=main_keyboard())
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка анализа: {str(e)}")
        await message.answer("❌ Инструмент не найден или недостаточно данных", reply_markup=main_keyboard())
        await state.clear()


@router.message(F.text == "↩️ Назад")
async def back_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_keyboard())