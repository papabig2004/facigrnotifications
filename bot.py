import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
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

# Простой HTTP-сервер для health check (нужен для Render Web Service)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass  # Отключаем логирование HTTP-запросов

def start_health_server():
    """Запускает простой HTTP-сервер для health check"""
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Health check server started on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    # Запускаем health check сервер в фоне
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
