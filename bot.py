import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# Токен вашего бота
API_TOKEN = os.getenv("API_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Команда start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Привет! Напиши что-то, и я добавлю кнопку 'Обработано'.")

# Функция для обработки сообщений
@dp.message_handler()
async def handle_message(message: types.Message):
    # Создаем кнопку "Обработано"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message.message_id}"))
    
    # Отправляем сообщение с кнопкой
    await message.answer(message.text, reply_markup=markup)

# Обработчик нажатия на кнопку
@dp.callback_query_handler(lambda c: c.data.startswith('done_'))
async def process_done(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])
    # Отправляем обновленное сообщение с галочкой
    await bot.edit_message_text(
        "✅ Обработано",
        chat_id=callback_query.message.chat.id,
        message_id=message_id
    )
    # Уведомление о нажатии
    await callback_query.answer("Сообщение помечено как обработано!")

if __name__ == '__main__':
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
