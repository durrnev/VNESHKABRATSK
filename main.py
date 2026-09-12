import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- НАСТРОЙКИ ---
# Токен берем из переменных окружения (это безопасно и решит ошибку Token is invalid)
BOT_TOKEN = os.getenv("8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg")
# ВАЖНО: Замените на ваш цифровой ID (можно узнать у бота @userinfobot)
ADMIN_ID = 8764200820 
# Юзернейм канала (без @), куда будут публиковаться посты
CHANNEL_USERNAME = "VNESHKABRATSK"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- МАШИНА СОСТОЯНИЙ (FSM) ---
class PostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()

# --- КЛАВИАТУРЫ ---
def get_admin_review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками Одобрить/Отклонить"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{post_id}")
        ]
    ])
    return keyboard

# --- ХЕНДЛЕРЫ (ОБРАБОТЧИКИ) ---

@dp.message(CommandStart())
async def command_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для отправки постов.\n\n"
        "Отправь мне фото, чтобы начать модерацию."
    )

@dp.message(F.photo)
async def handle_photo_start(message: types.Message, state: FSMContext):
    # Если пользователь уже в процессе создания поста
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("Вы уже создаете пост. Сначала завершите его или напишите /cancel.")
        return

    photo = message.photo[-1]  # Берем фото наилучшего качества
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(PostCreation.waiting_for_caption)
    await message.answer("Фото принято! Теперь напишите текст описания к посту.")

@dp.message(PostCreation.waiting_for_caption)
async def process_caption(message: types.Message, state: FSMContext):
    caption_text = message.text.strip()
    data = await state.get_data()
    photo_file_id = data.get('photo_file_id')

    if not photo_file_id:
        await state.clear()
        await message.answer("Произошла ошибка. Начните заново с отправки фото.")
        return

    # Формируем сообщение для админа
    draft_text = (
        f"<b>📨 Новый пост на проверку</b>\n\n"
        f"{caption_text}\n\n"
        f"Отправитель: <code>{message.from_user.id}</code>"
    )

    try:
        # Отправляем пост админу с кнопками
        sent_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file_id,
            caption=draft_text,
            reply_markup=get_admin_review_keyboard(message.message_id), # Используем ID сообщения юзера как ID поста
            parse_mode="HTML"
        )
        await message.answer("✅ Ваш пост отправлен на модерацию администратору.")
        await state.clear()
    except Exception as e:
        logging.error(f"Ошибка отправки поста админу: {e}")
        await message.answer("❌ Произошла ошибка при отправке на модерацию. Попробуйте позже.")
        await state.clear()

@dp.message(CommandStart())
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("❌ Создание поста отменено.")

# --- ОБРАБОТКА КНОПОК (CALLBACK QUERY) ---

@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    logging.info(f"Кнопка 'Одобрить' нажата пользователем {callback.from_user.id}")
    
    # Проверка прав администратора
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ У вас нет прав для модерации!", show_alert=True)
        return

    try:
        # ИСПРАВЛЕНИЕ ОШИБКИ: берем часть после разделителя и конвертируем в int
        # callback.data выглядит как "approve_12345", split("_", 1) вернет ["approve", "12345"]
        post_id = int(callback.data.split("_", 1)) [1](https://tr-page.yandex.ru/translate?lang=en-ru&url=https%3A%2F%2Fwww.geeksforgeeks.org%2Fpython%2Fkeyboard-buttons-in-telegram-bot-using-python%2F)
        logging.info(f"Одобрение поста ID: {post_id}")

        # Получаем оригинальное сообщение (текст и фото) из истории, чтобы переслать его
        # Примечание: В простой реализации без БД мы не можем легко достать фото снова.
        # Поэтому в этом примере мы просто публикуем текст из подписи сообщения админа.
        # Для полноценной работы нужно сохранять фото в файловую систему или базу данных.
        
        original_caption = callback.message.caption
        
        # Удаляем кнопки и ставим статус
        await callback.message.edit_caption(
            caption=f"{original_caption}\n\n✅ <b>Статус: Одобрено и опубликовано</b>",
            reply_markup=None,
            parse_mode="HTML"
        )

        # Публикация в канал
        try:
            await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=callback.message.photo[-1].file_id, # Пересылаем фото из сообщения админа
                caption=original_caption,
                parse_mode="HTML"
            )
            await callback.answer("Пост опубликован в канале!")
        except Exception as e:
            logging.error(f"Ошибка публикации в канал: {e}")
            await callback.answer("Пост одобрен, но не удалось опубликовать в канале (проверьте права бота).", show_alert=True)

    except ValueError:
        logging.error("Ошибка преобразования ID поста в число.")
        await callback.answer("Ошибка данных кнопки.", show_alert=True)
    except Exception as e:
        logging.error(f"Критическая ошибка в approve_post: {e}")
        await callback.answer("Произошла ошибка при обработке.", show_alert=True)

@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: types.CallbackQuery):
    logging.info(f"Кнопка 'Отклонить' нажата пользователем {callback.from_user.id}")

    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ У вас нет прав для модерации!", show_alert=True)
        return

    try:
        post_id = int(callback.data.split("_", 1)) [1](https://tr-page.yandex.ru/translate?lang=en-ru&url=https%3A%2F%2Fwww.geeksforgeeks.org%2Fpython%2Fkeyboard-buttons-in-telegram-bot-using-python%2F)
        logging.info(f"Отклонение поста ID: {post_id}")

        original_caption = callback.message.caption

        await callback.message.edit_caption(
            caption=f"{original_caption}\n\n❌ <b>Статус: Отклонено администратором</b>",
            reply_markup=None,
            parse_mode="HTML"
        )
        await callback.answer("Пост отклонен.")

    except Exception as e:
        logging.error(f"Ошибка в reject_post: {e}")
        await callback.answer("Произошла ошибка при отклонении.", show_alert=True)

# --- ЗАПУСК ---
async def main():
    logging.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
