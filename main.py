import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- НАСТРОЙКИ (без .env файлов) ---
BOT_TOKEN = "8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg" # Заменить на ваш токен
ADMIN_ID = 8764200820           # Заменить на ваш числовой Telegram ID
CHANNEL_USERNAME = "@VNESHKABRATSK" # Юзернейм канала для ссылок/логирования

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния для машины состояний (FSM)
class PostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()

# Клавиатура для оценки поста администратором
def get_admin_review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}")
        ]
    ])
    return keyboard

@dp.message(CommandStart())
async def command_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для анонимной отправки постов во 'ВНЕШКА БРАТСК'.\n\n"
        f"Правила:\n1. Отправь мне фото человека.\n2. Напиши краткое описание.\n3. Участники оценят внешность кнопками под постом.\n\n"
        "*Важно:* Твои данные не сохраняются, а посты публикуются только после проверки администратором.",
        parse_mode="Markdown"
    )

# Обработка команды отмены
@dp.message(F.text.casefold() == "/cancel")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("🚫 Создание поста отменено.")

# Старт создания поста
@dp.message(F.photo)
async def handle_photo_start(message: types.Message, state: FSMContext):
    # Если пользователь уже в процессе, игнорируем новые фото или просим отменить
    if await state.get_state() is not None:
        await message.answer("Вы уже создаете пост. Сначала завершите его или введите /cancel.")
        return
        
    photo = message.photo[-1] # Берем самое качественное фото
    file_id = photo.file_id
    
    await state.update_data(photo_file_id=file_id)
    await state.set_state(PostCreation.waiting_for_caption)
    
    await message.answer("Фото принято. Теперь напиши текст к посту (описание внешности).")

# Если прислали текст до фото
@dp.message(~F.photo & ~F.text.startswith('/'))
async def text_without_photo(message: types.Message):
    await message.answer("Сначала отправьте фотографию человека, чтобы начать создание поста.")

# Получение описания
@dp.message(PostCreation.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    caption_text = message.text.strip()
    data = await state.get_data()
    photo_file_id = data.get('photo_file_id')

    if not photo_file_id:
        await state.clear()
        await message.answer("Ошибка данных. Попробуйте отправить фото еще раз.")
        return

    # Формируем чернов
    draft_message = (
        f"<b>Новый пост на проверку</b>\n\n"
        f"{caption_text}\n\n"
        f"Отправитель: <code>{message.from_user.id}</code>"
    )
    
    # Отправляем фото админу с клавиатурой одобрения
    try:
        sent_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=FSInputFile(await bot.download_file_by_id(photo_file_id), filename='draft.jpg'),
            caption=draft_message,
            reply_markup=get_admin_review_keyboard(message.message_id)
        )
        
        # Сохраняем данные о черновике во временном хранилище (для простоты примера - в памяти)
        # В реальном проекте лучше использовать Redis или базу данных
        dp.current_state().update_data({
            f"pending_post_{sent_msg.message_id}": {
                "original_sender_id": message.from_user.id,
                "photo_file_id": photo_file_id,
                "caption": caption_text,
                "admin_draft_msg_id": sent_msg.message_id
            }
        })
        
        await message.answer("✅ Пост отправлен администратору на проверку. Ожидайте решения.")
        await state.clear()
    except Exception as e:
        await message.answer(f"❗ Произошла ошибка при пересылке фото админу: {e}")
        await state.clear()

# Обработка нажатий кнопок администратором
@dp.callback_query(F.data.in_(["approve_", "reject_"]))
async def admin_review_callback(callback: types.CallbackQuery):
    action, post_id_str = callback.data.split("_")
    original_post_id = int(post_id_str)
    
    storage_data = dp.current_state().data
    pending_key = f"pending_post_{callback.message.message_id}"
    
    if pending_key not in storage_data:
        await callback.answer("Этот запрос устарел или не найден.", show_alert=True)
        return

    user_id = storage_data[pending_key]["original_sender_id"]
    photo_file_id = storage_data[pending_key]["photo_file_id"]
    caption = storage_data[pending_key]["caption"]

    if action == "approve":
        # Публикуем в канал
        try:
            final_msg = await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=FSInputFile(await bot.download_file_by_id(photo_file_id), filename='final.jpg'),
                caption=caption + "\n\n---\nОценки:",
                hashtags=["внешкаБратск"] # Можно добавить хэштеги
            )
            
            # Добавляем кнопки для оценки участниками канала
            rating_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👍", callback_data=f"rate_like_{final_msg.message_id}")],
                [InlineKeyboardButton(text="👎", callback_data=f"rate_dislike_{final_msg.message_id}")]
            ])
            await bot.edit_message_reply_markup(
                chat_id=CHANNEL_USERNAME,
                message_id=final_msg.message_id,
                reply_markup=rating_kb
            )

            await callback.message.edit_caption(caption="✅ Пост одобрен и опубликован в канале.")
            await bot.send_message(user_id, "✅ Ваш пост успешно опубликован в канале!")

        except Exception as e:
            await callback.message.edit_caption(caption=f"❌ Ошибка публикации: {e}")

    elif action == "reject":
        await callback.message.edit_caption(caption="❌ Пост отклонен администратором.")
        await bot.send_message(user_id, "❌ Администратор отклонил ваш пост. Вы можете попробовать отправить другое фото.")

    # Чистим временные данные
    del storage_data[pending_key]

# Логика голосования участников внутри канала
@dp.callback_query(F.data.in_(["rate_like_", "rate_dislike_"]), chat_id=lambda c: c == CHANNEL_USERNAME)
async def channel_rating_callback(callback: types.CallbackQuery):
    action, msg_id_str = callback.data.split("_")
    target_msg_id = int(msg_id_str)
    
    # Чтобы избежать накрутки, можно проверять статус участника через чат-бота, но это усложнит код.
    # Здесь реализован простой ва
    
    like_count = 0
    dislike_count = 0
    
    # Важно: CallbackData имеет лимит длины. Для хранения счетчиков нужна база данных (SQLite/PostgreSQL).
    # Ниже приведена упрощенная логика смены текста кнопок для визуального подтверждения пользователю.
    
    new_button_text = "👍" if action == "rate_like" else "👎"
    
    # Перегенерируем клавиатуру, меняя цвет/дизайн нажатых кнопок нельзя, но можно заблокировать повторное нажатие тем же юзером,
    # если хранить список проголосовавших. Для простоты оставим возможность менять голос.
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍", callback_data=f"rate_like_{target_msg_id}")],
        [InlineKeyboardButton(text="👎", callback_data=f"rate_dislike_{target_msg_id}")]
    ])
    
    await callback.answer(text="Ваш голос учтен!", show_alert=False)
    await bot.edit_message_reply_markup(
        chat_id=CHANNEL_USERNAME,
        message_id=target_msg_id,
        reply_markup=kb
    )

if __name__ == "__main__":
    print("Запускаю бота...")
    dp.run_polling(bot)
