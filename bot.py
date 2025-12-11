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
    # Получаем текст сообщения
    message_text = message.text or message.caption or ""
    
    # Пропускаем команду /start
    if message_text.startswith('/start'):
        return
    
    # Создаем кнопку "Обработано"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message.message_id}"))
    
    # Сначала пытаемся отредактировать исходное сообщение (если оно от бота)
    try:
        if message.text:
            # Для текстовых сообщений
            await bot.edit_message_text(
                message_text,
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=markup
            )
            logging.info(f"Успешно отредактировано исходное сообщение {message.message_id}")
        elif message.caption:
            # Для сообщений с подписью
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=message_text,
                reply_markup=markup
            )
            logging.info(f"Успешно отредактирована подпись сообщения {message.message_id}")
    except Exception as e:
        # Если не удалось отредактировать (сообщение не от бота или другая ошибка),
        # отправляем новое сообщение с кнопкой
        logging.warning(f"Не удалось отредактировать сообщение {message.message_id}: {e}. Отправляем новое сообщение.")
        sent_message = await message.answer(message_text, reply_markup=markup)
        
        # Обновляем callback_data с правильным message_id нового сообщения
        markup_updated = InlineKeyboardMarkup()
        markup_updated.add(InlineKeyboardButton("Обработано", callback_data=f"done_{sent_message.message_id}"))
        
        try:
            if sent_message.text:
                await bot.edit_message_text(
                    message_text,
                    chat_id=sent_message.chat.id,
                    message_id=sent_message.message_id,
                    reply_markup=markup_updated
                )
        except Exception as e2:
            logging.warning(f"Не удалось обновить callback_data нового сообщения: {e2}")

# Обработчик нажатия на кнопку
@dp.callback_query_handler(lambda c: c.data.startswith('done_'))
async def process_done(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    
    # Получаем исходный message_id из callback_data (может быть исходное или новое сообщение)
    try:
        original_message_id = int(callback_query.data.split('_')[1])
    except (ValueError, IndexError):
        original_message_id = message_id
    
    # Получаем текст сообщения с кнопкой
    original_text = callback_query.message.text or callback_query.message.caption or ""
    
    # Добавляем галочку в конец текста, если её еще нет
    if not original_text.endswith(" ✅"):
        updated_text = original_text + " ✅"
    else:
        updated_text = original_text
    
    # Редактируем сообщение, добавляя галочку и убирая кнопку
    try:
        if callback_query.message.text:
            # Для текстовых сообщений
            await bot.edit_message_text(
                updated_text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None  # Убираем кнопку
            )
        elif callback_query.message.caption:
            # Для сообщений с подписью
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=updated_text,
                reply_markup=None  # Убираем кнопку
            )
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения: {e}")
        await callback_query.answer("Ошибка при обработке сообщения", show_alert=True)
        return
    
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
