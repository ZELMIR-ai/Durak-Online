import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8753178779:AAGGGUHjCOKVlBg7pxlQRX1BKL-MUCHgwdo")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://zelmir-ai.github.io/Durak-Html/")  # URL вашего фронтенда

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🃏 Играть в Дурака",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={message.from_user.id}&username={message.from_user.first_name}")
        )],
        [InlineKeyboardButton(text="📖 Правила", callback_query_data="rules")],
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "🃏 *Дурак* — классическая русская карточная игра!\n\n"
        "Выбери режим:\n"
        "• 🎲 *Рандом* — играй с незнакомцами\n"
        "• 👥 *С друзьями* — создай комнату и пригласи друзей\n\n"
        "Нажми кнопку ниже, чтобы начать!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@dp.callback_query(lambda c: c.data == "rules")
async def show_rules(callback: types.CallbackQuery):
    rules_text = (
        "📖 *Правила Дурака*\n\n"
        "🎯 *Цель:* избавиться от всех карт\n\n"
        "🃏 *Колода:* 36 карт (от 6 до туза)\n\n"
        "▶️ *Подкидной дурак:*\n"
        "• Атакующий кладёт карту, защищающийся отбивает старшей картой той же масти или козырем\n"
        "• Другие игроки могут подкидывать карты той же номинальной стоимости\n"
        "• Если защищающийся не может отбить — берёт все карты\n\n"
        "🔄 *Переводной дурак:*\n"
        "• Дополнительно: защищающийся может перевести атаку, положив карту того же достоинства\n"
        "• Перевод идёт следующему игроку по кругу\n\n"
        "♠️ *Козырь:* масть последней карты колоды\n\n"
        "🏆 *Победа:* последний оставшийся с картами — дурак!"
    )
    await callback.message.answer(rules_text, parse_mode="Markdown")
    await callback.answer()


@dp.message(Command("play"))
async def cmd_play(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🃏 Открыть игру",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={message.from_user.id}&username={message.from_user.first_name}")
        )]
    ])
    await message.answer("Нажми, чтобы открыть игру:", reply_markup=keyboard)


async def main():
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
