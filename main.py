import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8870850351:AAFkim_yrVbzm0Hm29qMsGMfL-aQr0mbuVg"
CHANNEL_ID = -1004396197440    
ADMIN_IDS = [8764200820]        

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния для участника
class ContestStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State() # Опционально, если хотите спрашивать ник

# Словарь для хранения постов, которые ждут одобрения
# Ключ: message_id превью у админа
pending_posts = {}

def get_admin_kb(preview_msg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{preview_msg_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{preview_msg_id}")
        ]
    ])

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! \n\n"
        "Чтобы предложить участника на оценку:\n"
        "1. Отправь мне его фото.\n"
        "2. Напиши имя или никнейм.\n\n"
        "*Важно:* Пост появится в канале только после проверки администратором."
    )
    await ContestStates.waiting_for_photo.set()

@dp.message(F.photo, StateFilter(ContestStates.waiting_for_photo))
async def receive_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await message.answer("Фото принято! Теперь напиши имя и сколько лет.")
    await ContestStates.waiting_for_name.set()

@dp.message(F.text, StateFilter(ContestStates.waiting_for_name))
async def receive_name_and_send_to_admin(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    photo_id = user_data.get('photo_file_id')
    name_text = message.text.strip()
    
    if not photo_id:
        await message.answer("Произошла ошибка с фото. Попробуй отправить команду /start еще раз.")
        await state.clear()
        return

    # Формируем пост для канала, но пока не отправляем туда
    caption = f"👤 На рассмотрении:\n\nИмя/Ник: {name_text}\nПредложил: @{message.from_user.username or message.from_user.first_name}"
    
    # Отправляем ПРЕВЬЮ ТОЛЬКО АДМИНУ
    preview_msg = await bot.send_photo(
        chat_id=ADMIN_IDS[0], 
        photo=photo_id, 
        caption=caption,
        reply_markup=get_admin_kb(0) # ID сообщения подставим позже через редактирование
    )

    # Сохраняем информацию о предложении до решения админа
    pending_posts[preview_msg.message_id] = {
        'proposer_id': message.from_user.id,
        'photo_id': photo_id,
        'name': name_text,
        'original_caption': caption
    }

    # ВАЖНО: редактируем сообщение, чтобы кнопки заработали (callback привязан к ID сообщения)
    await preview_msg.edit_reply_markup(reply_markup=get_admin_kb(preview_msg.message_id))

    await message.answer("✅ Твой пост отправлен на проверку администратору!")
    await state.clear()

@dp.callback_query(lambda c: c.data and (c.data.startswith("approve_") or c.data.startswith("reject_")))
async def admin_decision(callback: types.CallbackQuery):
    action, msg_id_str = callback.data.split('_')
    msg_id = int(msg_id_str)

    post_data = pending_posts.get(msg_id)
    if not post_data:
        await callback.answer("Эт


от пост уже обработан или срок ожидания истек.", show_alert=True)
        return

    try:
        if action == "approve":
            # Публикуем в канал
            final_caption = f"Оценка внешности:\n\n📛 Имя/Ник: {post_data['name']}\n➕ Предложил: <a href='tg://user?id={post_data['proposer_id']}'>участник</a>"
            
            sent_channel_msg = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=post_data['photo_id'],
                caption=final_caption,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[]]) # Можно добавить сюда те же кнопки голосования из прошлого кода
            )
            await callback.answer(f"✅ Пост опубликован! (ID: {sent_channel_msg.message_id})")
            
        else: # reject
            await callback.answer("❌ Пост отклонен.")

        # Удаляем превью у админа и чистим память
        try:
            await bot.delete_message(chat_id=ADMIN_IDS[0], message_id=msg_id)
        except Exception:
            pass # Если сообщение уже удалено
            
        if msg_id in pending_posts:
            del pending_posts[msg_id]

    except Exception as e:
        await callback.answer(f"Ошибка публикации: {e}", show_alert=True)

async def main():
    print("Бот-модератор запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
