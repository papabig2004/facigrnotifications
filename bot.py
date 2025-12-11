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
from aiogram.dispatcher.middlewares import BaseMiddleware

# Токен вашего бота
API_TOKEN = os.getenv("API_TOKEN")
# ID чата для проверки сообщений (из настроек Bitrix)
CHAT_ID = int(os.getenv("CHAT_ID", "447824223"))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
# Устанавливаем бота в контекст глобально (нужно для aiogram 2.x при использовании webhook)
Bot.set_current(bot)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Добавляем кастомный middleware для логирования всех обновлений
class UpdateLoggingMiddleware(BaseMiddleware):
    async def on_process_message(self, message, data):
        logging.info(f"[Middleware] Обрабатывается сообщение: message_id={message.message_id}, "
                    f"from_user={message.from_user.id if message.from_user else None}, "
                    f"is_bot={message.from_user.is_bot if message.from_user else None}")
        return data

dp.middleware.setup(UpdateLoggingMiddleware())

# Команда start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Привет! Напиши что-то, и я добавлю кнопку 'Обработано'.")

# Функция для обработки всех типов сообщений
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_message(message: types.Message):
    # Логируем получение сообщения ВСЕГДА (даже если не обрабатываем)
    logging.info(f"[handle_message] Получено сообщение: message_id={message.message_id}, chat_id={message.chat.id}, "
                 f"from_user={message.from_user.id if message.from_user else None}, "
                 f"is_bot={message.from_user.is_bot if message.from_user else None}, "
                 f"content_type={message.content_type}, "
                 f"text_length={len(message.text) if message.text else 0}")
    
    # ВАЖНО: Обрабатываем ТОЛЬКО сообщения от бота (от Bitrix)
    # Bitrix отправляет сообщения от имени бота, поэтому проверяем is_bot
    if not message.from_user:
        logging.warning(f"[handle_message] Сообщение без from_user: message_id={message.message_id}")
        return
    
    if not message.from_user.is_bot:
        logging.info(f"[handle_message] Пропущено сообщение от пользователя (не от бота): message_id={message.message_id}, from_user={message.from_user.id}, username={message.from_user.username}")
        return
    
    logging.info(f"[handle_message] Обрабатываем сообщение от бота (Bitrix): message_id={message.message_id}, bot_id={message.from_user.id}, bot_username={message.from_user.username}")
    
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
    # Используем message_id исходного сообщения в callback_data
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message.message_id}"))
    
    logging.info(f"Создана кнопка для сообщения {message.message_id}")
    
    # ВСЕГДА пытаемся отредактировать исходное сообщение (от Bitrix)
    # Bitrix отправляет сообщения от имени бота, поэтому бот может их редактировать
    try:
        if message.text:
            # Для текстовых сообщений - редактируем исходное сообщение, добавляя кнопку
            await bot.edit_message_text(
                message_text,  # Текст остается тот же, только добавляется кнопка
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=markup
            )
            logging.info(f"Успешно отредактировано исходное сообщение {message.message_id}, добавлена кнопка")
        elif message.caption:
            # Для сообщений с подписью
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=message_text,
                reply_markup=markup
            )
            logging.info(f"Успешно отредактирована подпись сообщения {message.message_id}, добавлена кнопка")
    except Exception as e:
        # Если не удалось отредактировать (редкий случай - сообщение не от бота),
        # отправляем новое сообщение с кнопкой как fallback
        logging.warning(f"Не удалось отредактировать сообщение {message.message_id}: {e}. Отправляем новое сообщение.")
        sent_message = await message.answer(message_text, reply_markup=markup)
        logging.info(f"Отправлено новое сообщение {sent_message.message_id} с кнопкой")

# Обработчик нажатия на кнопку
@dp.callback_query_handler(lambda c: c.data.startswith('done_'))
async def process_done(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id  # Сообщение, на котором была кнопка
    
    # Получаем текст сообщения (то, на котором была кнопка)
    original_text = callback_query.message.text or callback_query.message.caption or ""
    
    # Убираем галочку, если она уже есть (на случай повторного нажатия)
    if original_text.endswith(" ✅"):
        original_text = original_text[:-2].rstrip()
    
    # Добавляем галочку в конец текста
    updated_text = original_text + " ✅"
    
    # Редактируем сообщение, на котором была кнопка
    # Это исходное сообщение от Bitrix (если кнопка была добавлена к нему)
    # или новое сообщение (если исходное не удалось отредактировать)
    try:
        if callback_query.message.text:
            # Для текстовых сообщений
            await bot.edit_message_text(
                updated_text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None  # Убираем кнопку
            )
            logging.info(f"Успешно отредактировано сообщение {message_id}, добавлена галочка, убрана кнопка")
        elif callback_query.message.caption:
            # Для сообщений с подписью
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=updated_text,
                reply_markup=None  # Убираем кнопку
            )
            logging.info(f"Успешно отредактирована подпись сообщения {message_id}, добавлена галочка, убрана кнопка")
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения {message_id}: {e}")
        await callback_query.answer("Ошибка при обработке сообщения", show_alert=True)
        return
    
    # Уведомление о нажатии
    await callback_query.answer("Сообщение помечено как обработано!")

# Множество для отслеживания обработанных сообщений (чтобы не обрабатывать повторно)
processed_messages = set()
# Последний проверенный update_id (чтобы проверять только новые сообщения)
last_checked_update_id = 0

async def check_and_add_buttons():
    """Периодически проверяет последние сообщения в чате и добавляет кнопки к тем, у которых их нет"""
    global processed_messages, last_checked_update_id
    
    try:
        # Получаем последние обновления (но не обрабатываем их через диспетчер)
        # Используем offset, чтобы получать только новые сообщения
        updates = await bot.get_updates(offset=last_checked_update_id + 1, limit=10, timeout=1)
        
        for update in updates:
            # Обновляем последний проверенный update_id
            if update.update_id > last_checked_update_id:
                last_checked_update_id = update.update_id
            
            if update.message and update.message.chat.id == CHAT_ID:
                message = update.message
                message_id = message.message_id
                
                # Пропускаем, если уже обработали
                if message_id in processed_messages:
                    continue
                
                # Пропускаем, если сообщение от пользователя (не от бота)
                if not message.from_user or not message.from_user.is_bot:
                    continue
                
                # Пропускаем команды
                message_text = message.text or message.caption or ""
                if message_text.startswith('/'):
                    continue
                
                # Пропускаем, если нет текста
                if not message_text:
                    continue
                
                # Проверяем, есть ли уже кнопка у сообщения
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
                    logging.info(f"[check_and_add_buttons] Добавляем кнопку к сообщению {message_id}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("Обработано", callback_data=f"done_{message_id}"))
                    
                    try:
                        if message.text:
                            await bot.edit_message_text(
                                message_text,
                                chat_id=CHAT_ID,
                                message_id=message_id,
                                reply_markup=markup
                            )
                            logging.info(f"[check_and_add_buttons] Успешно добавлена кнопка к сообщению {message_id}")
                        elif message.caption:
                            await bot.edit_message_caption(
                                chat_id=CHAT_ID,
                                message_id=message_id,
                                caption=message_text,
                                reply_markup=markup
                            )
                            logging.info(f"[check_and_add_buttons] Успешно добавлена кнопка к сообщению {message_id}")
                        
                        # Помечаем как обработанное
                        processed_messages.add(message_id)
                    except Exception as e:
                        logging.warning(f"[check_and_add_buttons] Не удалось добавить кнопку к сообщению {message_id}: {e}")
    except Exception as e:
        logging.error(f"[check_and_add_buttons] Ошибка при проверке сообщений: {e}")

async def periodic_check():
    """Периодически проверяет сообщения в чате"""
    while True:
        try:
            await check_and_add_buttons()
            # Проверяем каждые 5 секунд
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"[periodic_check] Ошибка: {e}")
            await asyncio.sleep(5)

# HTTP-сервер для webhook и health check

async def health_check(request):
    """Health check endpoint для Render"""
    return web.Response(text="OK")

async def webhook_handler(request):
    """Обработчик webhook от Telegram"""
    try:
        update_data = await request.json()
        update = types.Update(**update_data)
        
        # Логируем полученное обновление
        if update.message:
            logging.info(f"[webhook_handler] Получено обновление с сообщением: message_id={update.message.message_id}, "
                        f"from_user={update.message.from_user.id if update.message.from_user else None}, "
                        f"is_bot={update.message.from_user.is_bot if update.message.from_user else None}")
        elif update.callback_query:
            logging.info(f"[webhook_handler] Получено обновление с callback_query: data={update.callback_query.data}")
        else:
            logging.info(f"[webhook_handler] Получено обновление другого типа: {type(update)}")
        
        # Устанавливаем текущий экземпляр бота в контекст (нужно для aiogram 2.x)
        # Это должно быть сделано перед обработкой обновления в каждом запросе
        Bot.set_current(bot)
        
        # Обрабатываем обновление
        await dp.process_update(update)
        
        logging.info(f"[webhook_handler] Обновление обработано успешно")
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
            
            # Запускаем периодическую проверку сообщений в фоне
            asyncio.create_task(periodic_check())
            logging.info("Запущена периодическая проверка сообщений (каждые 5 секунд)")
            
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
        
        # Запускаем периодическую проверку сообщений в отдельном потоке
        async def run_periodic_check():
            await periodic_check()
        
        def start_periodic_check_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_periodic_check())
        
        periodic_thread = threading.Thread(target=start_periodic_check_thread, daemon=True)
        periodic_thread.start()
        logging.info("Запущена периодическая проверка сообщений (каждые 5 секунд)")
        
        # Запуск бота с polling
        executor.start_polling(
            dp, 
            skip_updates=True,
            allowed_updates=['message', 'callback_query'],
            timeout=20,
            relax=0.1
        )
