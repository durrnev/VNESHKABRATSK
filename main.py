import logging
import os
import asyncio
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg"  # ⚠️ Замени на новый токен!
ADMIN_ID = 8764200820
CHANNEL_USERNAME = "@VNESHKABRATSK"

# Папка для кэширования фото
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# Временное хранилище: {post_id: {"photo_path": str, "caption": str, "user_id": int}}
pending_posts: dict = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# --- FSM СОСТОЯНИЯ ---
class PostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def download_photo(bot: Bot, file_id: str, save_path: Path) -> bool:
    """Скачивает фото по file_id и сохраняет в save_path. Возвращает True при успехе."""
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


# --- ХЭНДЛЕРЫ ---

@dp.message(CommandStart())
async def command_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для анонимной отправки постов во 'ВНЕШКА БРАТСК'.\n\n"
        "Правила:\n"
        "1. Отправь мне фото человека.\n"
        "2. Напиши краткое описание.\n"
        "3. Участники оценят внешность кнопками под постом.\n\n"
        "*Важно:* Твои данные не сохраняются, а посты публикуются только после проверки администратором.",
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
    await message.answer("Фото принято. Теперь напиши текст к посту (описание внешности).")


@dp.message(PostCreation.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    caption_text = message.text.strip()
    data = await state.get_data()
    photo_path = data.get("photo_path")

    if not photo_path or not os.path.exists(photo_path):
        await state.clear()
        await message.answer("Ошибка: файл фото не найден. Попробуй отправить фото ещё раз.")
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

        # Сохраняем данные поста во временное хранилище
        pending_posts[post_id] = {
            "photo_path": photo_path,
            "caption": caption_text,
            "user_id": message.from_user.id,
            "admin_message_id": sent_msg.message_id,
        }

        await message.answer("✅ Фото и описание отправлены на модерацию. Ожидайте решения администратора.")
    except Exception as e:
        logging.error(f"Ошибка отправки поста админу: {e}")
        await message.answer("❌ Произошла ошибка при отправке на модерацию. Попробуй позже.")

    await state.clear()


@dp.message(~F.photo & ~F.text.startswith("/") & ~PostCreation.waiting_for_caption)
async def text_without_photo(message: types.Message):
    await message.answer("Сначала отправьте фотографию человека, чтобы начать создание поста.")


# --- CALLBACK: ОДОБРЕНИЕ ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("Пост не найден в памяти. Возможно, бот был перезапущен.")
        return

    photo_path = post_data["photo_path"]
    caption = post_data["caption"]

    if not os.path.exists(photo_path):
        await callback.answer("Файл фото не найден на диске.")
        return

    channel_message = f"{caption}\n\n#ВНЕШКАБРАТСК"

    try:
        await bot.send_photo(
            chat_id=CHANNEL_USERNAME,
            photo=FSInputFile(photo_path),
            caption=channel_message,
            reply_markup=get_channel_rating_keyboard(),
            parse_mode="HTML",
        )

        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>Статус: Одобрено и опубликовано в канал</b>",
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer("Пост одобрен и опубликован!")

        # Уведомляем отправителя
        try:
            await bot.send_message(
                post_data["user_id"],
                "✅ Твой пост одобрен и опубликован в канале!",
            )
        except Exception:
            pass  # Пользователь мог заблокировать бота

    except Exception as e:
        logging.error(f"Ошибка публикации в канал: {e}")
        await callback.answer("Ошибка при публикации в канал. Проверь, добавлен ли бот в админы канала.")

    # Удаляем фото из кэша
    try:
        os.remove(photo_path)
    except Exception as e:
        logging.warning(f"Не удалось удалить файл {photo_path}: {e}")

    # Удаляем из временного хранилища
    pending_posts.pop(post_id, None)


# --- CALLBACK: ОТКЛОНЕНИЕ ---
@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: types.CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("Пост не найден в памяти. Возможно, бот был перезапущен.")
        return

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>Статус: Отклонено</b>",
        reply_markup=None,
        parse_mode="HTML",
    )
    await callback.answer("Пост отклонён.")

    # Уведомляем отправителя
    try:
        await bot.send_message(
            post_data["user_id"],
            "❌ Твой пост отклонён администратором.",
        )
    except Exception:
        pass

    # Удаляем фото из кэша
    photo_path = post_data.get("photo_path")
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception as e:
            logging.warning(f"Не удалось удалить файл {photo_path}: {e}")

    pending_posts.pop(post_id, None)


# --- РЕЙТИНГ В КАНАЛЕ ---
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
    else:
        await callback.answer("Неизвестная оценка")


# --- ЗАПУСК ---
async def main():
    logging.info("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
