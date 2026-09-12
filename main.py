import logging
import os
import asyncio
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- НАСТРОЙКИ ---
# ⚠️ СРОЧНО: замените это на реальный токен!
BOT_TOKEN = "8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg" 
ADMIN_ID = 8764200820  # Вставьте сюда свой реальный ID
CHANNEL_USERNAME = "VNESHKABRATSK"

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

pending_posts: dict = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class PostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()

async def download_photo(bot: Bot, file_id: str, save_path: Path) -> bool:
    try:
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, save_path)
        return True
    except Exception as e:
        logging.error(f"Ошибка скачивания фото: {e}")
        return False

def get_admin_review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}"),
        ]
    ])
    return keyboard

def get_channel_rating_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 10/10", callback_data="rating_10"),
            InlineKeyboardButton(text="👍 Хорошо", callback_data="rating_good"),
            InlineKeyboardButton(text="👎 Мимо", callback_data="rating_bad"),
        ]
    ])
    return keyboard

@dp.message(CommandStart())
async def command_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для анонимной отправки постов.\n\n"
        "1. Отправь фото.\n"
        "2. Напиши описание.\n"
        "3. Админ проверит, и пост уйдет в канал.",
        parse_mode="Markdown",
    )

@dp.message(F.text.casefold() == "/cancel")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("🚫 Создание поста отменено.")

@dp.message(F.photo)
async def handle_photo_start(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await message.answer("Вы уже создаёте пост. Сначала завершите его или введите /cancel.")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    unique_name = f"{int(datetime.now().timestamp())}_{message.from_user.id}_{message.message_id}.jpg"
    save_path = CACHE_DIR / unique_name

    if not await download_photo(bot, file_id, save_path):
        await message.answer("❌ Не удалось сохранить фото. Попробуйте ещё раз.")
        return

    await state.update_data(photo_file_id=file_id, photo_path=str(save_path))
    await state.set_state(PostCreation.waiting_for_caption)
    await message.answer("Фото принято. Теперь напиши текст к посту.")

@dp.message(PostCreation.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    caption_text = message.text.strip()
    data = await state.get_data()
    photo_path = data.get("photo_path")

    if not photo_path or not os.path.exists(photo_path):
        await state.clear()
        await message.answer("Ошибка: файл фото не найден. Попробуй сначала отправить фото.")
        return

    draft_message = (
        f"<b>Новый пост на проверку</b>\n\n"
        f"{caption_text}\n\n"
        f"Отправитель: <code>{message.from_user.id}</code>"
    )

    post_id = message.message_id

    try:
        sent_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=FSInputFile(photo_path),
            caption=draft_message,
            reply_markup=get_admin_review_keyboard(post_id),
            parse_mode="HTML",
        )

        pending_posts[post_id] = {
            "photo_path": photo_path,
            "caption": caption_text,
            "user_id": message.from_user.id,
            "admin_message_id": sent_msg.message_id,
        }

        await message.answer("✅ Фото и описание отправлены на модерацию.")
    except Exception as e:
        logging.error(f"Ошибка отправки поста админу: {e}")
        await message.answer("❌ Произошла ошибка при отправке на модерацию. Попробуй позже.")

    await state.clear()

@dp.message(~F.photo & ~F.text.startswith("/"))
async def text_without_photo(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == PostCreation.waiting_for_caption:
        return
    await message.answer("Сначала отправьте фотографию человека.")

# --- ИСПРАВЛЕННЫЕ ХЭНДЛЕРЫ КНОПОК ---

@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    logging.info(f"Запрос на одобрение от {callback.from_user.id}")
    try:
        # ИСПРАВЛЕНИЕ ЗДЕСЬ: добавлено для получения строки с ID
        post_id = int(callback.data.split("_", 1))
    except (ValueError, IndexError):
        await callback.answer("Некорректный ID поста.", show_alert=True)
        return

    post_data = pending_posts.get(post_id)
    if not post_data:
        await callback.answer("Пост не найден в памяти.", show_alert=True)
        return

    photo_path = post_data["photo_path"]
    if not os.path.exists(photo_path):
        await callback.answer("Файл фото не найден.", show_alert=True)
        _cleanup_post(post_id, photo_path)
        return

    try:
        await bot.send_photo(
            chat_id=CHANNEL_USERNAME,
            photo=FSInputFile(photo_path),
            caption=f"{post_data['caption']}\n\n#ВНЕШКАБРАТСК",
            reply_markup=get_channel_rating_keyboard(),
            parse_mode="HTML",
        )

        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>Статус: Одобрено и опубликовано</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer("Пост опубликован!")

        try:
            await bot.send_message(post_data["user_id"], "✅ Твой пост опубликован!")
        except:
            pass

    except Exception as e:
        logging.error(f"Ошибка публикации: {e}")
        await callback.answer(f"Ошибка публикации: {str(e)}", show_alert=True)

    _cleanup_post(post_id, photo_path)

@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: types.CallbackQuery):
    logging.info(f"Запрос на отклонение от {callback.from_user.id}")
    try:
        # ИСПРАВЛЕНИЕ ЗДЕСЬ: добавлено для получения строки с ID
        post_id = int(callback.data.split("_", 1))
    except (ValueError, IndexError):
        await callback.answer("Некорректный ID поста.", show_alert=True)
        return

    post_data = pending_posts.get(post_id)
    if not post_data:
        await callback.answer("Пост не найден в памяти.", show_alert=True)
        return

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>Статус: Отклонено</b>",
        reply_markup=None,
        parse_mode="HTML",
    )
    await callback.answer("Пост отклонён.")

    try:
        await bot.send_message(post_data["user_id"], "❌ Твой пост отклонён.")
    except:
        pass

    _cleanup_post(post_id, post_data.get("photo_path"))

def _cleanup_post(post_id: int, photo_path: str | None):
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception as e:
            logging.warning(f"Не удалось удалить файл: {e}")
    pending_posts.pop(post_id, None)

@dp.callback_query(F.data.startswith("rating_"))
async def handle_rating(callback: types.CallbackQuery):
    rating_map = {
        "rating_10": "🔥 10/10",
        "rating_good": "👍 Хорошо",
        "rating_bad": "👎 Мимо",
    }
    choice = rating_map.get(callback.data)
    if choice:
        await callback.answer(f"Ты оценил: {choice}")

async def main():
    logging.info("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
