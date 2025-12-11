import os
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiohttp import web
from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Токен вашего бота
API_TOKEN = os.getenv("API_TOKEN")
# ID чата для проверки сообщений
CHAT_ID = int(os.getenv("CHAT_ID", "447824223"))
# URL для webhook (должен быть установлен в Render)
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=API_TOKEN)
Bot.set_current(bot)  # Нужно для aiogram 2.x

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

# HTTP-сервер для webhook и health check
async def health_check(request):
    """Health check endpoint для Render"""
    return web.Response(text="OK")

async def webhook_handler(request):
    """Обработчик webhook от Telegram"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        
        # Устанавливаем бота в контекст
        Bot.set_current(bot)
        
        # Обрабатываем сообщения
        if update.message:
            if update.message.chat.id == CHAT_ID:
                await process_message(update.message)
        
        # Обрабатываем нажатия на кнопки
        elif update.callback_query:
            if update.callback_query.data.startswith('done_'):
                await process_callback_query(update.callback_query)
        
        return web.Response(text='{"ok":true}')
    except Exception as e:
        logging.error(f"Ошибка при обработке webhook: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return web.Response(text='{"ok":false}', status=500)

def create_app():
    """Создает aiohttp приложение"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_post('/webhook', webhook_handler)
    return app

async def main():
    """Главная функция"""
    if not WEBHOOK_URL:
        logging.error("WEBHOOK_URL не установлен! Установите переменную окружения WEBHOOK_URL в Render.")
        logging.error("Например: https://your-service.onrender.com")
        return
    
    # Удаляем существующий webhook перед установкой нового
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logging.info(f"Найден активный webhook: {webhook_info.url}. Удаляем...")
            await bot.delete_webhook()
            logging.info("Webhook удален успешно")
    except Exception as e:
        logging.warning(f"Ошибка при проверке/удалении webhook: {e}")
    
    # Устанавливаем webhook
    webhook_path = f"{WEBHOOK_URL}/webhook"
    await bot.set_webhook(webhook_path)
    logging.info(f"Webhook установлен: {webhook_path}")
    
    # Запускаем HTTP-сервер
    app = create_app()
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"HTTP-сервер запущен на порту {port}")
    logging.info("Бот готов к работе. Ожидаю обновления через webhook...")
    
    # Держим программу запущенной
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logging.info("Остановка бота...")
        await bot.delete_webhook()
        await runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
