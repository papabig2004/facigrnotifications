import os
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Токен вашего бота
API_TOKEN = os.getenv("API_TOKEN")
# ID чата для проверки сообщений
CHAT_ID = int(os.getenv("CHAT_ID", "447824223"))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=API_TOKEN)

# Множество для отслеживания обработанных сообщений
processed_messages = set()

async def add_button_to_message(message_id, message_text, is_caption=False):
    """Добавляет кнопку 'Обработано' к сообщению"""
    try:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message_id}"))
        
        if is_caption:
            await bot.edit_message_caption(
                chat_id=CHAT_ID,
                message_id=message_id,
                caption=message_text,
                reply_markup=markup
            )
        else:
            await bot.edit_message_text(
                message_text,
                chat_id=CHAT_ID,
                message_id=message_id,
                reply_markup=markup
            )
        
        logging.info(f"Кнопка добавлена к сообщению {message_id}")
        processed_messages.add(message_id)
        return True
    except Exception as e:
        logging.warning(f"Не удалось добавить кнопку к сообщению {message_id}: {e}")
        return False

async def process_message(message):
    """Обрабатывает сообщение: проверяет, нужно ли добавить кнопку"""
    message_id = message.message_id
    
    # Пропускаем, если уже обработали
    if message_id in processed_messages:
        return
    
    # Пропускаем, если сообщение не от бота (Bitrix отправляет от имени бота)
    if not message.from_user or not message.from_user.is_bot:
        return
    
    # Получаем текст сообщения
    message_text = message.text or message.caption or ""
    
    # Пропускаем команды и пустые сообщения
    if not message_text or message_text.startswith('/'):
        return
    
    # Проверяем, есть ли уже кнопка "Обработано"
    has_button = False
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for button in row:
                if button.text == "Обработано":
                    has_button = True
                    break
            if has_button:
                break
    
    # Если кнопки нет - добавляем
    if not has_button:
        is_caption = bool(message.caption)
        await add_button_to_message(message_id, message_text, is_caption)

async def process_callback_query(callback_query):
    """Обрабатывает нажатие на кнопку 'Обработано'"""
    message = callback_query.message
    message_id = message.message_id
    
    # Получаем текст сообщения
    original_text = message.text or message.caption or ""
    
    # Убираем галочку, если она уже есть
    if original_text.endswith(" ✅"):
        original_text = original_text[:-2].rstrip()
    
    # Добавляем галочку в конец текста
    updated_text = original_text + " ✅"
    
    # Редактируем сообщение: убираем кнопку и добавляем галочку
    try:
        if message.text:
            await bot.edit_message_text(
                updated_text,
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=None
            )
        elif message.caption:
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message_id,
                caption=updated_text,
                reply_markup=None
            )
        
        # Уведомляем пользователя
        await bot.answer_callback_query(callback_query.id, text="Сообщение помечено как обработано!")
        logging.info(f"Сообщение {message_id} помечено как обработано")
    except Exception as e:
        logging.error(f"Ошибка при обработке кнопки для сообщения {message_id}: {e}")
        await bot.answer_callback_query(callback_query.id, text="Ошибка при обработке", show_alert=True)

async def check_messages():
    """Главный цикл: получает обновления и обрабатывает их"""
    last_update_id = 0
    
    while True:
        try:
            # Получаем обновления
            updates = await bot.get_updates(offset=last_update_id + 1, limit=100, timeout=10)
            
            for update in updates:
                # Обновляем последний обработанный update_id
                if update.update_id > last_update_id:
                    last_update_id = update.update_id
                
                # Обрабатываем сообщения
                if update.message:
                    # Проверяем только сообщения в нужном чате
                    if update.message.chat.id == CHAT_ID:
                        await process_message(update.message)
                
                # Обрабатываем нажатия на кнопки
                elif update.callback_query:
                    if update.callback_query.data.startswith('done_'):
                        await process_callback_query(update.callback_query)
                
        except Exception as e:
            logging.error(f"Ошибка в главном цикле: {e}")
            await asyncio.sleep(5)

# Простой HTTP-сервер для health check (нужен для Render Web Service)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        pass

def start_health_server():
    """Запускает простой HTTP-сервер для health check"""
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Health check server started on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    # Удаляем существующий webhook
    async def delete_existing_webhook():
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logging.info(f"Найден активный webhook: {webhook_info.url}. Удаляем...")
                await bot.delete_webhook()
                logging.info("Webhook удален успешно")
        except Exception as e:
            logging.warning(f"Ошибка при проверке/удалении webhook: {e}")
    
    asyncio.run(delete_existing_webhook())
    
    # Запускаем health check сервер в фоне
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Запускаем главный цикл проверки сообщений
    logging.info("Бот запущен. Проверяю сообщения в чате...")
    asyncio.run(check_messages())
