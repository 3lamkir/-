import asyncio
import aiohttp
import json
import time
from datetime import datetime
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask
from threading import Thread

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Файлы для хранения данных
WHITELIST_FILE = 'whitelist.json'
APPROVED_CHANNELS_FILE = 'approved_channels.json'
STATS_FILE = 'stats.json'
PENDING_CHANNELS_FILE = 'pending_channels.json'

# Веб-сервер для Replit
app = Flask('')

@app.route('/')
def home():
    return "🌿 Garden Stock Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

class GardenStockBot:
    def __init__(self):
        self.whitelist = self.load_json(WHITELIST_FILE, [])
        self.approved_channels = self.load_json(APPROVED_CHANNELS_FILE, {})
        self.pending_channels = self.load_json(PENDING_CHANNELS_FILE, {})
        self.stats = self.load_json(STATS_FILE, {
            'start_time': time.time(),
            'total_messages_sent': 0,
            'channels_approved': 0,
            'restart_count': 0
        })
        self.proctor_items = self.load_proctor_items()
        self.last_stock = {}
        self.last_messages = {}
        self.stock_check_task = None

    def load_json(self, filename, default):
        """Загружает данные из JSON файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def save_json(self, filename, data):
        """Сохраняет данные в JSON файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения {filename}: {e}")
            return False

    def load_proctor_items(self):
        """Загружает список отслеживаемых предметов - ИСПРАВЛЕНО ДЛЯ REPLIT"""
        try:
            # Сначала пробуем загрузить из файла
            if os.path.exists('proctor.txt'):
                with open('proctor.txt', 'r', encoding='utf-8') as f:
                    items = []
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            clean_item = ' '.join(line.split()).lower()
                            items.append(clean_item)
                    
                    logger.info(f"🎯 Загружено {len(items)} предметов из proctor.txt")
                    logger.info(f"📝 Предметы: {items}")
                    return items
            else:
                # Если файла нет, создаем пример
                default_items = [
                    "seed packet",
                    "watering can", 
                    "garden glove",
                    "plant food",
                    "pruning shear"
                ]
                with open('proctor.txt', 'w', encoding='utf-8') as f:
                    for item in default_items:
                        f.write(item + '\n')
                logger.info(f"📝 Создан файл proctor.txt с примерами предметов")
                return default_items
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки proctor.txt: {e}")
            return ["seed packet", "watering can"]  # Fallback items

    def is_whitelisted(self, user_id):
        """Проверяет, есть ли пользователь в белом списке"""
        return str(user_id) in self.whitelist

    def add_to_whitelist(self, user_id, username="Unknown"):
        """Добавляет пользователя в белый список"""
        user_id_str = str(user_id)
        if user_id_str not in self.whitelist:
            self.whitelist.append(user_id_str)
            if self.save_json(WHITELIST_FILE, self.whitelist):
                logger.info(f"✅ Добавлен в белый список: {user_id_str} ({username})")
                return True
        return False

    def remove_from_whitelist(self, user_id):
        """Удаляет пользователя из белого списка"""
        user_id_str = str(user_id)
        if user_id_str in self.whitelist:
            self.whitelist.remove(user_id_str)
            if self.save_json(WHITELIST_FILE, self.whitelist):
                logger.info(f"❌ Удален из белого списка: {user_id_str}")
                return True
        return False

    def add_pending_channel(self, channel_id, channel_title, invited_by, invite_link=None):
        """Добавляет канал в ожидание одобрения"""
        self.pending_channels[str(channel_id)] = {
            'title': channel_title,
            'invited_by': invited_by,
            'request_time': time.time(),
            'invite_link': invite_link
        }
        if self.save_json(PENDING_CHANNELS_FILE, self.pending_channels):
            logger.info(f"⏳ Канал в ожидании: {channel_title} (ID: {channel_id})")
            return True
        return False

    def remove_pending_channel(self, channel_id):
        """Удаляет канал из ожидания"""
        channel_id_str = str(channel_id)
        if channel_id_str in self.pending_channels:
            del self.pending_channels[channel_id_str]
            if self.save_json(PENDING_CHANNELS_FILE, self.pending_channels):
                logger.info(f"🗑️ Удален из ожидания: {channel_id_str}")
                return True
        return False

    def add_approved_channel(self, channel_id, channel_title, approved_by):
        """Добавляет одобренный канал"""
        self.approved_channels[str(channel_id)] = {
            'title': channel_title,
            'approved_at': time.time(),
            'approved_by': approved_by
        }
        self.stats['channels_approved'] = len(self.approved_channels)
        if self.save_json(APPROVED_CHANNELS_FILE, self.approved_channels):
            self.save_json(STATS_FILE, self.stats)
            logger.info(f"✅ Канал одобрен: {channel_title} (ID: {channel_id})")
            return True
        return False

    def remove_approved_channel(self, channel_id):
        """Удаляет одобренный канал"""
        channel_id_str = str(channel_id)
        if channel_id_str in self.approved_channels:
            del self.approved_channels[channel_id_str]
            self.stats['channels_approved'] = len(self.approved_channels)
            if self.save_json(APPROVED_CHANNELS_FILE, self.approved_channels):
                self.save_json(STATS_FILE, self.stats)
                logger.info(f"❌ Канал удален: {channel_id_str}")
                return True
        return False

    async def get_real_garden_stock(self):
        """Получает данные стока из Grow A Garden API - ИСПРАВЛЕНО ДЛЯ REPLIT"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://growagarden.gg/',
            'Origin': 'https://growagarden.gg'
        }
        
        try:
            # Добавляем таймауты для Replit
            timeout = aiohttp.ClientTimeout(total=15)
            
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get('https://growagarden.gg/api/stock') as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Успешно получены данные API")
                        return self.parse_stock_data(data)
                    else:
                        logger.error(f"❌ Ошибка API: {response.status}")
                        return {}
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при запросе к API")
            return {}
        except Exception as e:
            logger.error(f"❌ Ошибка получения стока: {e}")
            return {}

    def parse_stock_data(self, data):
        """Парсит данные стока и фильтрует по proctor.txt - ИСПРАВЛЕНО"""
        stock_items = {}
        
        try:
            logger.info(f"🔍 Начинаем парсинг данных...")
            
            # Разные возможные структуры ответа API
            if isinstance(data, list):
                # Если данные пришли как список
                stock_data = data
            elif 'result' in data and 'data' in data['result']:
                # Если структура с result.data
                stock_data = data['result']['data']
            elif 'data' in data:
                # Если структура с data
                stock_data = data['data']
            else:
                # Пробуем обработать как есть
                stock_data = data
            
            if not stock_data:
                logger.warning("⚠️ Данные стока пусты")
                return {}
                
            logger.info(f"📊 Обрабатываем {len(stock_data)} элементов стока")
            
            found_count = 0
            for item in stock_data:
                try:
                    name = item.get('name', '').lower().strip()
                    quantity = item.get('quantity', 0)
                    
                    # Логируем для отладки
                    if name in self.proctor_items:
                        logger.info(f"🎯 Найден отслеживаемый предмет: {name} - {quantity} шт.")
                    
                    if name in self.proctor_items and quantity > 0:
                        stock_items[name] = quantity
                        found_count += 1
                        
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки элемента: {e}")
                    continue
                    
            logger.info(f"✅ Найдено {found_count} отслеживаемых предметов в стоке")
            return stock_items
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга данных: {e}")
            return {}

    def format_stock_message(self, new_items):
        """Форматирует красивое сообщение о стоке"""
        if not new_items:
            return None
            
        if len(new_items) == 1:
            title = "🎯 *НОВЫЙ ПРЕДМЕТ В СТОКЕ!*\n\n"
        else:
            title = f"🎯 *НОВЫЕ ПРЕДМЕТЫ В СТОКЕ!* ({len(new_items)} шт.)\n\n"
        
        items_text = ""
        for item_name, quantity in new_items.items():
            display_name = item_name.title()  # Capitalize each word
            items_text += f"🟢 *{display_name}* — `{quantity}` шт.\n"
        
        message = f"{title}{items_text}\n⏰ *Обновлено:* {datetime.now().strftime('%H:%M:%S')}"
        return message

    def find_new_items(self, current_stock):
        """Находит новые предметы по сравнению с предыдущей проверкой"""
        new_items = {}
        
        for item_name, quantity in current_stock.items():
            if item_name not in self.last_stock:
                new_items[item_name] = quantity
                logger.info(f"🆕 Новый предмет обнаружен: {item_name} - {quantity} шт.")
                
        self.last_stock = current_stock.copy()
        return new_items

    async def send_stock_updates(self, application, new_items):
        """Отправляет обновления во все одобренные каналы - ИСПРАВЛЕНО"""
        if not new_items:
            return
            
        message = self.format_stock_message(new_items)
        if not message:
            return
            
        sent_count = 0
        failed_channels = []
        
        logger.info(f"📨 Начинаем отправку в {len(self.approved_channels)} каналов")
        
        for channel_id, channel_info in list(self.approved_channels.items()):
            try:
                logger.info(f"🔄 Пытаемся отправить в канал: {channel_info['title']} (ID: {channel_id})")
                
                # Пытаемся отправить сообщение
                sent_message = await application.bot.send_message(
                    chat_id=channel_id, 
                    text=message, 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                
                self.last_messages[str(channel_id)] = sent_message.message_id
                sent_count += 1
                
                logger.info(f"✅ Сообщение отправлено в канал {channel_info['title']}")
                await asyncio.sleep(1)  # Задержка между отправками
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Ошибка отправки в канал {channel_id}: {error_msg}")
                
                # Если бот не в канале или нет прав, удаляем канал из одобренных
                if "Chat not found" in error_msg or "bot is not a member" in error_msg or "Forbidden" in error_msg:
                    failed_channels.append(channel_id)
                    logger.warning(f"🗑️ Удаляем канал {channel_id} из одобренных")
        
        # Удаляем проблемные каналы
        for channel_id in failed_channels:
            self.remove_approved_channel(channel_id)
        
        if sent_count > 0:
            self.stats['total_messages_sent'] += sent_count
            self.save_json(STATS_FILE, self.stats)
            logger.info(f"📊 Итог отправки: {sent_count} успешно, {len(failed_channels)} неудачно")

    async def check_stock_loop(self, application):
        """Основной цикл проверки стока - УЛУЧШЕННАЯ ВЕРСИЯ"""
        logger.info("🔄 Запущен цикл проверки стока")
        
        check_count = 0
        error_count = 0
        
        while True:
            try:
                if error_count > 5:
                    logger.warning("🔄 Перезапуск цикла проверки из-за множественных ошибок")
                    error_count = 0
                
                current_stock = await self.get_real_garden_stock()
                
                if current_stock:
                    new_items = self.find_new_items(current_stock)
                    
                    if new_items:
                        logger.info(f"🎁 Найдены новые предметы: {list(new_items.keys())}")
                        await self.send_stock_updates(application, new_items)
                        error_count = 0  # Сбрасываем счетчик ошибок при успехе
                    else:
                        check_count += 1
                        if check_count % 10 == 0:  # Логируем каждые 10 проверок
                            logger.info("🔍 Проверка стока - новых предметов нет")
                            logger.info(f"📊 Текущий сток: {len(current_stock)} предметов")
                else:
                    logger.warning("⚠️ Не удалось получить данные стока")
                    error_count += 1
                
                # Ждем перед следующей проверкой
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле проверки: {e}")
                error_count += 1
                await asyncio.sleep(60)  # Увеличиваем задержку при ошибках

    def get_bot_stats(self):
        """Получает статистику бота"""
        uptime = time.time() - self.stats['start_time']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        
        return f"""
🌿 GARDEN STOCK BOT - СТАТИСТИКА 🌿

⏰ Время работы: {hours:02d}:{minutes:02d}:{seconds:02d}
📊 Каналов одобрено: {self.stats['channels_approved']}
📨 Сообщений отправлено: {self.stats['total_messages_sent']}
👥 Администраторов: {len(self.whitelist)}
🎯 Отслеживаемых предметов: {len(self.proctor_items)}
⏳ Заявок на рассмотрении: {len(self.pending_channels)}

🟢 Статус: Активен
🕒 Последняя проверка: {datetime.now().strftime('%H:%M:%S')}
        """

# Создаем экземпляр бота
bot = GardenStockBot()

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if not bot.is_whitelisted(user_id):
        welcome_text = f"""
🌿 Добро пожаловать, {username}! 🌿

🤖 *Garden Stock Bot* - автоматический отслеживатель стока предметов в игре *Grow A Garden*.

✨ *Что умеет бот:*
• Автоматически проверяет сток каждые 30 секунд
• Отправляет уведомления только о новых предметах
• Работает 24/7 и не пропустит ни одного обновления

📝 *Как подать заявку на подключение:*
Просто используйте команду /request и следуйте инструкциям!

❌ *У вас нет доступа к управлению ботом.*
*Для подачи заявки используйте команду /request*
        """
        keyboard = [
            [InlineKeyboardButton("📋 Подать заявку", callback_data="make_request")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help_public")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        return
        
    # Приветствие для администратора
    admin_welcome = f"""
🌟 Добро пожаловать, администратор {username}! 🌟

🤖 Garden Stock Bot готов к работе!

📊 Текущая статистика:
• Каналов одобрено: {len(bot.approved_channels)}
• Предметов отслеживается: {len(bot.proctor_items)}
• Заявок на рассмотрении: {len(bot.pending_channels)}

🛠 Доступные команды:

📈 Информация:
/stats - Подробная статистика
/channels - Одобренные каналы  
/pending - Заявки на одобрение

⚙️ Управление:
/approve <ID> - Одобрить канал
/reject <ID> - Отклонить канал
/addadmin <ID> - Добавить админа
/removeadmin <ID> - Удалить админа
/listadmins - Список админов

❓ Помощь:
/help - Полный список команд

💡 Бот уже работает и отслеживает сток!
    """
    
    stats = bot.get_bot_stats()
    await update.message.reply_text(admin_welcome)
    await update.message.reply_text(stats)

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для подачи заявки на подключение канала"""
    user = update.effective_user
    user_id = user.id
    
    # Создаем уникальный ID для заявки
    request_id = int(time.time())
    
    instruction_text = f"""
📨 ФОРМА ЗАЯВКИ НА ПОДКЛЮЧЕНИЕ

👤 *Заявитель:* {user.first_name}
🆔 *ID:* `{user_id}`
📋 *ID заявки:* `{request_id}`

📝 *Инструкция по подаче заявки:*

1. *Добавьте бота в ваш канал* как администратора:
   - Права на отправку сообщений
   - Права на удаление сообщений

2. *Пришлите сюда:*
   - Название вашего канала
   - ID канала (если знаете)
   - Ссылку-приглашение в канал

3. *Пример заполнения:*

⏳ *После отправки данных заявка будет рассмотрена в течение 24 часов*

💡 *Как найти ID канала:*
• Добавьте @username_to_id_bot в канал
• Или перешлите сообщение из канала боту @userinfobot
    """
    
    # Сохраняем информацию о том, что пользователь начал заполнять заявку
    context.user_data['making_request'] = True
    context.user_data['request_id'] = request_id
    
    keyboard = [
        [InlineKeyboardButton("❌ Отменить заявку", callback_data="cancel_request")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(instruction_text, reply_markup=reply_markup)

async def handle_request_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает данные заявки от пользователя"""
    user = update.effective_user
    user_id = user.id
    text = update.message.text
    
    # Проверяем, заполняет ли пользователь заявку
    if not context.user_data.get('making_request'):
        return
    
    # Парсим данные заявки
    lines = text.split('\n')
    channel_data = {
        'name': '',
        'id': '',
        'link': '',
        'user_id': user_id,
        'username': user.first_name,
        'request_time': time.time()
    }
    
    for line in lines:
        line = line.strip()
        if line.startswith('Название:'):
            channel_data['name'] = line.replace('Название:', '').strip()
        elif line.startswith('ID:'):
            channel_data['id'] = line.replace('ID:', '').strip()
        elif 't.me/' in line or 'https://' in line:
            channel_data['link'] = line.strip()
    
    # Проверяем, что все обязательные поля заполнены
    if not channel_data['name']:
        await update.message.reply_text("❌ Пожалуйста, укажите название канала в формате:\n`Название: Ваше название канала`")
        return
    
    # Создаем заявку
    request_id = context.user_data.get('request_id', int(time.time()))
    channel_id = channel_data['id'] or f"pending_{request_id}"
    
    # Добавляем заявку в ожидание
    invited_by = f"{user.first_name} (ID: {user_id})"
    if bot.add_pending_channel(channel_id, channel_data['name'], invited_by, channel_data['link']):
        # Очищаем данные пользователя
        context.user_data.pop('making_request', None)
        context.user_data.pop('request_id', None)
        
        # Подтверждаем пользователю
        success_text = f"""
✅ ЗАЯВКА УСПЕШНО ПОДАНА!

📋 *Данные заявки:*
• Название: {channel_data['name']}
• ID: `{channel_id}`
• Ссылка: {channel_data['link'] or 'Не указана'}
• Номер заявки: `{request_id}`

⏳ *Заявка будет рассмотрена администраторами в течение 24 часов.*

💬 *Статус заявки можно уточнить у администратора.*
        """
        
        await update.message.reply_text(success_text)
        
        # Уведомляем администраторов
        notification_text = f"""
📨 НОВАЯ ЗАЯВКА НА ПОДКЛЮЧЕНИЕ!

📋 *Данные заявки:*
• Название: {channel_data['name']}
• ID: `{channel_id}`
• Ссылка: {channel_data['link'] or 'Не указана'}
• Заявитель: {user.first_name}
• ID заявителя: `{user_id}`
• Номер заявки: `{request_id}`

💬 *Для рассмотрения заявки используйте:*
/pending
        """
        
        for admin_id in bot.whitelist:
            try:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=notification_text
                )
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить администратора {admin_id}: {e}")
                
        logger.info(f"✅ Новая заявка от {user.first_name}: {channel_data['name']}")
        
    else:
        await update.message.reply_text("❌ Произошла ошибка при создании заявки. Попробуйте еще раз.")

async def cancel_request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет заполнение заявки"""
    if context.user_data.get('making_request'):
        context.user_data.pop('making_request', None)
        context.user_data.pop('request_id', None)
        await update.message.reply_text("❌ Заполнение заявки отменено.")
    else:
        await update.message.reply_text("ℹ️ У вас нет активных заявок для отмены.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику бота"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    stats = bot.get_bot_stats()
    await update.message.reply_text(stats)

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список одобренных каналов"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not bot.approved_channels:
        await update.message.reply_text("📭 Нет одобренных каналов.")
        return
        
    channels_list = "✅ ОДОБРЕННЫЕ КАНАЛЫ:\n\n"
    for channel_id, channel_info in bot.approved_channels.items():
        approved_time = datetime.fromtimestamp(channel_info['approved_at']).strftime('%d.%m.%Y %H:%M')
        channels_list += f"📢 {channel_info['title']}\n🆔 `{channel_id}`\n⏰ Одобрен: {approved_time}\n\n"
    
    await update.message.reply_text(channels_list)

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает каналы в ожидании одобрения"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not bot.pending_channels:
        await update.message.reply_text("⏳ Нет заявок на рассмотрении.")
        return
        
    pending_list = "⏳ ЗАЯВКИ НА РАССМОТРЕНИИ:\n\n"
    buttons = []
    
    for channel_id, channel_info in bot.pending_channels.items():
        request_time = datetime.fromtimestamp(channel_info['request_time']).strftime('%d.%m %H:%M')
        pending_list += f"📢 {channel_info['title']}\n🆔 `{channel_id}`\n👤 Добавил: {channel_info['invited_by']}\n⏰ Запрос: {request_time}\n\n"
        
        buttons.append([
            InlineKeyboardButton(f"✅ {channel_info['title'][:15]}", callback_data=f"approve:{channel_id}"),
            InlineKeyboardButton(f"❌ {channel_info['title'][:15]}", callback_data=f"reject:{channel_id}")
        ])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(pending_list, reply_markup=reply_markup)

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобряет канал по ID"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /approve <channel_id>")
        return
        
    channel_id = context.args[0]
    
    if channel_id not in bot.pending_channels:
        await update.message.reply_text("❌ Канал не найден в ожидании.")
        return
        
    channel_info = bot.pending_channels[channel_id]
    
    if bot.add_approved_channel(channel_id, channel_info['title'], f"user_{user_id}"):
        bot.remove_pending_channel(channel_id)
        
        # Пытаемся присоединиться к каналу если есть ссылка
        if channel_info.get('invite_link'):
            try:
                await context.bot.join_chat(channel_info['invite_link'])
                logger.info(f"✅ Бот присоединился к каналу {channel_info['title']}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось присоединиться к каналу: {e}")
        
        await update.message.reply_text(f"✅ Канал успешно одобрен!\n\n📢 {channel_info['title']}")
    else:
        await update.message.reply_text("❌ Ошибка при одобрении канала.")

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклоняет канал по ID"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /reject <channel_id>")
        return
        
    channel_id = context.args[0]
    
    if channel_id not in bot.pending_channels:
        await update.message.reply_text("❌ Канал не найден в ожидании.")
        return
        
    channel_info = bot.pending_channels[channel_id]
    
    if bot.remove_pending_channel(channel_id):
        await update.message.reply_text(f"❌ Запрос отклонен.\n\n📢 {channel_info['title']}")
    else:
        await update.message.reply_text("❌ Ошибка при отклонении канала.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    
    data = query.data
    
    if data == "make_request":
        await query.message.reply_text("📝 Используйте команду /request для подачи заявки на подключение канала.")
        await query.answer()
        return
        
    elif data == "help_public":
        help_text = """
❓ ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ:

🤖 *Что делает бот?*
- Отслеживает появление предметов в игре Grow A Garden
- Автоматически уведомляет каналы о новых предметах
- Работает 24/7

📝 *Как подать заявку?*
- Используйте команду /request
- Следуйте инструкциям в форме заявки
- Ожидайте одобрения администраторами

⏰ *Как часто проверяется сток?*
- Каждые 30 секунд

📨 *Куда приходят уведомления?*
- В одобренные каналы

🔧 *По вопросам подключения:* используйте команду /request
        """
        await query.message.reply_text(help_text)
        await query.answer()
        return
        
    elif data == "cancel_request":
        if context.user_data.get('making_request'):
            context.user_data.pop('making_request', None)
            context.user_data.pop('request_id', None)
            await query.message.edit_text("❌ Заполнение заявки отменено.")
        else:
            await query.answer("ℹ️ У вас нет активных заявок для отмены.")
        return
    
    # Остальная логика для администраторов
    if not bot.is_whitelisted(user_id):
        await query.answer("❌ У вас нет доступа!", show_alert=True)
        return
        
    await query.answer()
    
    if data.startswith('approve:'):
        channel_id = data.split(':')[1]
        
        if channel_id in bot.pending_channels:
            channel_info = bot.pending_channels[channel_id]
            
            if bot.add_approved_channel(channel_id, channel_info['title'], f"user_{user_id}"):
                bot.remove_pending_channel(channel_id)
                
                # Пытаемся присоединиться к каналу если есть ссылка
                if channel_info.get('invite_link'):
                    try:
                        await context.bot.join_chat(channel_info['invite_link'])
                        logger.info(f"✅ Бот присоединился к каналу {channel_info['title']}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось присоединиться к каналу: {e}")
                
                await query.edit_message_text(
                    f"✅ Канал успешно одобрен!\n\n"
                    f"📢 {channel_info['title']}\n"
                    f"🆔 `{channel_id}`"
                )
            else:
                await query.edit_message_text("❌ Ошибка при одобрении канала.")
        else:
            await query.edit_message_text("❌ Канал уже обработан или не найден!")
            
    elif data.startswith('reject:'):
        channel_id = data.split(':')[1]
        
        if channel_id in bot.pending_channels:
            channel_info = bot.pending_channels[channel_id]
            
            if bot.remove_pending_channel(channel_id):
                await query.edit_message_text(
                    f"❌ Запрос отклонен.\n\n"
                    f"📢 {channel_info['title']}\n"
                    f"🆔 `{channel_id}`"
                )
            else:
                await query.edit_message_text("❌ Ошибка при отклонении канала.")
        else:
            await query.edit_message_text("❌ Канал уже обработан или не найден!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку по командам"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        # Помощь для обычных пользователей
        help_text = """
🌿 GARDEN STOCK BOT - ПОМОЩЬ 🌿

🤖 *Что делает бот?*
Автоматически отслеживает появление новых предметов в игре Grow A Garden и уведомляет подключенные каналы.

📝 *Как подключить канал?*
Используйте команду /request и следуйте инструкциям!

⏰ *Частота проверок:* каждые 30 секунд
🕒 *Время работы:* 24/7

🔧 *По вопросам подключения:* используйте /request
        """
        await update.message.reply_text(help_text)
        return
        
    # Помощь для администраторов
    help_text = """
🌿 GARDEN STOCK BOT - КОМАНДЫ АДМИНИСТРАТОРА 🌿

📊 ИНФОРМАЦИЯ:
/start - Главное меню и приветствие
/stats - Подробная статистика бота
/channels - Список одобренных каналов
/pending - Заявки на одобрение

⚙️ УПРАВЛЕНИЕ КАНАЛАМИ:
/approve <ID> - Одобрить канал по ID
/reject <ID> - Отклонить канал по ID

👥 УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ:
/addadmin <ID> - Добавить администратора
/removeadmin <ID> - Удалить администратора
/listadmins - Список администраторов

❓ ПОМОЩЬ:
/help - Показать эту справку

📝 ПРОЦЕСС ПОДКЛЮЧЕНИЯ:
1. Пользователь использует /request
2. Заполняет форму заявки
3. Администратор проверяет заявки через /pending
4. Одобряет/отклоняет через кнопки

💡 Бот автоматически отслеживает сток каждые 30 секунд!
    """
    await update.message.reply_text(help_text)

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет администратора"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /addadmin <user_id>")
        return
        
    new_admin_id = context.args[0]
    username = update.effective_user.username or "Unknown"
    
    if bot.add_to_whitelist(new_admin_id, username):
        await update.message.reply_text(f"✅ Администратор добавлен!\n\n🆔 `{new_admin_id}`")
    else:
        await update.message.reply_text("❌ Ошибка при добавлении администратора.")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет администратора"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /removeadmin <user_id>")
        return
        
    remove_admin_id = context.args[0]
    
    if remove_admin_id == str(user_id):
        await update.message.reply_text("❌ Нельзя удалить самого себя!")
        return
        
    if bot.remove_from_whitelist(remove_admin_id):
        await update.message.reply_text(f"✅ Администратор удален!\n\n🆔 `{remove_admin_id}`")
    else:
        await update.message.reply_text("❌ Администратор не найден или ошибка удаления.")

async def list_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список администраторов"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not bot.whitelist:
        await update.message.reply_text("👥 В белом списке нет администраторов.")
        return
        
    admins_list = "👥 АДМИНИСТРАТОРЫ:\n\n"
    for admin_id in bot.whitelist:
        admins_list += f"▫️ `{admin_id}`\n"
    
    await update.message.reply_text(admins_list)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}", exc_info=context.error)

def setup_handlers(application):
    """Настраивает обработчики команд"""
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("request", request_command))
    application.add_handler(CommandHandler("cancelrequest", cancel_request_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("reject", reject_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("removeadmin", remove_admin_command))
    application.add_handler(CommandHandler("listadmins", list_admins_command))
    
    # Обработчик данных заявки
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_request_data
    ))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)

async def start_stock_checker(application):
    """Запускает проверку стока в фоне"""
    await asyncio.sleep(5)  # Ждем немного перед запуском
    await bot.check_stock_loop(application)

def main():
    """Запуск бота"""
    try:
        from config import BOT_TOKEN
        
        # Запускаем веб-сервер в отдельном потоке для Replit
        Thread(target=run_web, daemon=True).start()
        logger.info("🌐 Веб-сервер запущен на порту 8080")
        
        # Создаем приложение с Job Queue
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Настраиваем обработчики
        setup_handlers(application)
        
        # Запускаем проверку стока в фоне
        loop = asyncio.get_event_loop()
        loop.create_task(start_stock_checker(application))
        
        # Запускаем бота
        logger.info("🌿 Запускаем Garden Stock Bot...")
        logger.info("✅ Бот успешно запущен!")
        logger.info("📊 Статистика:")
        logger.info(f"   - Администраторов: {len(bot.whitelist)}")
        logger.info(f"   - Отслеживаемых предметов: {len(bot.proctor_items)}")
        logger.info(f"   - Одобренных каналов: {len(bot.approved_channels)}")
        logger.info(f"   - Заявок на рассмотрении: {len(bot.pending_channels)}")
        
        # Запускаем polling
        application.run_polling()
        
    except ImportError:
        logger.error("❌ Файл config.py не найден! Создайте его с BOT_TOKEN.")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")

if __name__ == '__main__':
    main()