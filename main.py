import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg"  # ⚠️ Вставь сюда новый токен!
ADMIN_ID = 8764200820         # ⚠️ Замени на свой ID
CHANNEL_USERNAME = "@VNESHKABRATSK"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния FSM
class PostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()

# Клавиатура для администратора
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
        "Правила:\n"
        "1. Отправь мне фото человека.\n"
        "2. Напиши краткое описание.\n"
        "3. Участники оценят внешность кнопками под постом.\n\n"
        "*Важно:* Твои данные не сохраняются, а посты публикуются только после проверки администратором.",
        parse_mode="Markdown"
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

    photo = message.photo[-1]  # Самое качественное фото
    file_id = photo.file_id
    await state.update_data(photo_file_id=file_id)
    await state.set_state(PostCreation.waiting_for_caption)
    await message.answer("Фото принято. Теперь напиши текст к посту (описание внешности).")

@dp.message(~F.photo & ~F.text.startswith('/'))
async def text_without_photo(message: types.Message):
    # Если пользователь пишет текст, но не начал создание поста
    await message.answer("Сначала отправьте фотографию человека, чтобы начать создание поста.")

@dp.message(PostCreation.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    caption_text = message.text.strip()
    data = await state.get_data()
    photo_file_id = data.get('photo_file_id')

    if not photo_file_id:
        await state.clear()
        await message.answer("Ошибка данных. Попробуйте отправить фото ещё раз.")
        return

    draft_message = (
        f"<b>Новый пост на проверку</b>\n\n"
        f"{caption_text}\n\n"
        f"Отправитель: <code>{message.from_user.id}</code>"
    )

    try:
        sent_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file_id,  # Отправляем по file_id — это быстрее и надёжнее
            caption=draft_message,
            reply_markup=get_admin_review_keyboard(message.message_id),
            parse_mode="HTML"
        )
        # Сохраняем данные о посте в контексте сообщения админа (через temp storage можно усложнить, но для примера — в памяти FSM не храним)
        # Для простоты: мы можем использовать message.message_id как ID поста
        await message.answer("✅ Фото и описание отправлены на модерацию. Ожидайте решения администратора.")
    except Exception as e:
        logging.error(f"Ошибка отправки поста админу: {e}")
        await message.answer("❌ Произошла ошибка при отправке на модерацию. Попробуйте позже.")

    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    post_id = callback.data.split("_")[1]
    # Здесь нужно получить данные поста (фото, текст). В текущей реализации они не сохранены.
    # Для полноценного бота нужно хранить черновики в базе данных или словаре.
    # Ниже — упрощённый пример: мы просто отвечаем, что пост одобрен, но не публикуем его.
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>Статус: Одобрено</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer("Пост одобрен!")
    # TODO: Здесь нужно реализовать отправку поста в канал CHANNEL_USERNAME

@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: types.CallbackQuery):
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>Статус: Отклонено</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer("Пост отклонён.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
