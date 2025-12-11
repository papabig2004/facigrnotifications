import os
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiohttp import web
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

# Функция для обработки всех типов сообщений
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_message(message: types.Message):
    # Логируем получение сообщения
    logging.info(f"Получено сообщение: message_id={message.message_id}, chat_id={message.chat.id}, "
                 f"from_user={message.from_user.id if message.from_user else None}, "
                 f"content_type={message.content_type}")
    
    # Получаем текст сообщения
    message_text = message.text or message.caption or ""
    
    if message_text:
        logging.info(f"Текст сообщения (первые 200 символов): {message_text[:200]}")
    else:
        logging.warning(f"Сообщение без текста: content_type={message.content_type}")
    
    # Пропускаем команду /start
    if message_text.startswith('/start'):
        logging.info("Пропущена команда /start")
        return
    
    # Если нет текста, пропускаем
    if not message_text:
        logging.warning(f"Пропущено сообщение без текста: message_id={message.message_id}")
        return
    
    # Создаем кнопку "Обработано"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message.message_id}"))
    
    logging.info(f"Создана кнопка для сообщения {message.message_id}")
    
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

# HTTP-сервер для webhook и health check

async def health_check(request):
    """Health check endpoint для Render"""
    return web.Response(text="OK")

async def webhook_handler(request):
    """Обработчик webhook от Telegram"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        
        # Устанавливаем текущий экземпляр бота в контекст (нужно для aiogram 2.x)
        Bot.set_current(bot)
        
        # Обрабатываем обновление
        await dp.process_update(update)
        return web.Response(text='{"ok":true}')
    except Exception as e:
        logging.error(f"Ошибка при обработке webhook: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return web.Response(text='{"ok":false}', status=500)

def create_webhook_app():
    """Создает aiohttp приложение для webhook"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_post('/webhook', webhook_handler)
    return app

async def start_webhook_server():
    """Запускает aiohttp сервер для webhook"""
    app = create_webhook_app()
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Webhook server started on port {port}")
    return runner

if __name__ == '__main__':
    import asyncio
    
    # Проверяем, используется ли webhook или polling
    webhook_url = os.getenv('WEBHOOK_URL')
    
    if webhook_url:
        # Используем webhook (для работы с Bitrix без конфликтов)
        logging.info(f"Настройка webhook на {webhook_url}")
        
        async def main():
            # Запускаем webhook сервер
            runner = await start_webhook_server()
            
            # Устанавливаем webhook в Telegram
            await bot.set_webhook(webhook_url + '/webhook')
            logging.info("Webhook установлен успешно")
            
            # Держим программу запущенной
            try:
                while True:
                    await asyncio.sleep(3600)  # Проверяем каждый час
            except KeyboardInterrupt:
                logging.info("Остановка бота...")
                await bot.delete_webhook()
                await runner.cleanup()
        
        asyncio.run(main())
    else:
        # Используем polling (если webhook не настроен)
        logging.info("Используется polling (webhook не настроен)")
        logging.warning("ВНИМАНИЕ: Если Bitrix тоже использует polling, будет конфликт!")
        
        # Удаляем существующий webhook перед использованием polling
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
        class HealthCheckHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'OK')
            def log_message(self, format, *args):
                pass
        
        def start_health_server():
            port = int(os.getenv('PORT', 10000))
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            logging.info(f"Health check server started on port {port}")
            server.serve_forever()
        
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
        
        # Запуск бота с polling
        executor.start_polling(
            dp, 
            skip_updates=True,
            allowed_updates=['message', 'callback_query'],
            timeout=20,
            relax=0.1
        )
