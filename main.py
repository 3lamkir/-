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
PROCTOR_FILE = 'proctor.json'

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
        """Загружает список отслеживаемых предметов из JSON"""
        try:
            if os.path.exists(PROCTOR_FILE):
                with open(PROCTOR_FILE, 'r', encoding='utf-8') as f:
                    proctor_data = json.load(f)
                
                items = proctor_data.get('tracked_items', [])
                self.check_interval = proctor_data.get('settings', {}).get('check_interval', 30)
                
                logger.info(f"🎯 Загружено {len(items)} предметов из proctor.json")
                logger.info(f"⏰ Интервал проверки: {self.check_interval} сек.")
                return items
            else:
                # Создаем файл по умолчанию с предметами из p.txt
                default_data = {
                    "tracked_items": [
                        "carrot", "strawberry", "blueberry", "orange tulip", "tomato", 
                        "corn", "daffodil", "watermelon", "pumpkin", "apple", "bamboo", 
                        "coconut", "cactus", "dragon fruit", "mango", "grape", "mushroom", 
                        "pepper", "cacao", "beanstalk", "ember lily", "sugar apple", 
                        "burning bud", "giant pinecone", "elder strawberry", "romanesco", 
                        "crimson thorn", "watering can", "trowel", "recall wrench", 
                        "basic sprinkler", "advanced sprinkler", "godly sprinkler", 
                        "magnifying glass", "tanning mirror", "master sprinkler", 
                        "cleaning spray", "favorite tool", "harvest tool", "friendship pot", 
                        "grantmaster sprinkler", "level lollipop", "common egg", 
                        "uncommon egg", "rare egg", "legendary egg", "mythical egg", 
                        "bug egg", "jungle egg"
                    ],
                    "settings": {
                        "check_interval": 30,
                        "notify_all_items": False,
                        "min_quantity": 1
                    },
                    "metadata": {
                        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "total_items": 49
                    }
                }
                
                with open(PROCTOR_FILE, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=2)
                
                logger.info("📝 Создан файл proctor.json с предметами из p.txt")
                self.check_interval = 30
                return default_data['tracked_items']
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки proctor.json: {e}")
            self.check_interval = 30
            return ["carrot", "tomato", "corn"]

    def save_proctor_items(self, items=None):
        """Сохраняет предметы в JSON файл"""
        try:
            if items is None:
                items = self.proctor_items
            
            proctor_data = {
                "tracked_items": items,
                "settings": {
                    "check_interval": getattr(self, 'check_interval', 30),
                    "notify_all_items": False,
                    "min_quantity": 1
                },
                "metadata": {
                    "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "total_items": len(items)
                }
            }
            
            with open(PROCTOR_FILE, 'w', encoding='utf-8') as f:
                json.dump(proctor_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Сохранено {len(items)} предметов в proctor.json")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения proctor.json: {e}")
            return False

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
        """Get real stock data from Grow A Garden API - NEW VERSION"""
        
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'priority': 'u=1, i',
            'referer': 'https://growagarden.gg/stocks',
            'trpc-accept': 'application/json',
            'x-trpc-source': 'gag',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get('https://growagarden.gg/api/stock') as response:
                    if response.status == 200:
                        raw_data = await response.json()
                        logger.info(f"✅ Успешно получены сырые данные API")
                        
                        # Сохраняем сырые данные для отладки
                        try:
                            with open('debug_stock_raw.json', 'w', encoding='utf-8') as f:
                                json.dump(raw_data, f, indent=2, ensure_ascii=False)
                            logger.info("💾 Сырые данные сохранены в debug_stock_raw.json")
                        except:
                            pass
                        
                        # Форматируем данные как в JavaScript коде
                        formatted_data = self.format_stocks(raw_data)
                        return self.parse_formatted_stock_data(formatted_data)
                    else:
                        logger.error(f"❌ Ошибка API: {response.status}")
                        return {}
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут при запросе к API")
            return {}
        except Exception as e:
            logger.error(f"❌ Ошибка получения стока: {e}")
            return {}

    def format_items(self, items, image_data=None, is_last_seen=False):
        """Форматирует items как в JavaScript коде"""
        if not isinstance(items, list) or len(items) == 0:
            return []
        
        formatted_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
                
            # Базовые поля
            name = item.get('name', 'Unknown')
            image = None
            if image_data and name in image_data:
                image = image_data[name]
            
            base_item = {'name': name}
            if image:
                base_item['image'] = image
            
            # Дополнительные поля в зависимости от типа
            if is_last_seen:
                formatted_item = {
                    **base_item,
                    'emoji': item.get('emoji', '❓'),
                    'seen': item.get('seen')
                }
            else:
                formatted_item = {
                    **base_item,
                    'value': item.get('value')
                }
            
            formatted_items.append(formatted_item)
        
        return formatted_items

    def format_stocks(self, stocks_data):
        """Форматирует стоки как в JavaScript коде"""
        image_data = stocks_data.get('imageData', {})
        
        formatted = {
            'easterStock': self.format_items(stocks_data.get('easterStock', []), image_data),
            'gearStock': self.format_items(stocks_data.get('gearStock', []), image_data),
            'eggStock': self.format_items(stocks_data.get('eggStock', []), image_data),
            'nightStock': self.format_items(stocks_data.get('nightStock', []), image_data),
            'honeyStock': self.format_items(stocks_data.get('honeyStock', []), image_data),
            'cosmeticsStock': self.format_items(stocks_data.get('cosmeticsStock', []), image_data),
            'seedsStock': self.format_items(stocks_data.get('seedsStock', []), image_data),
            
            'lastSeen': {
                'Seeds': self.format_items(stocks_data.get('lastSeen', {}).get('Seeds', []), image_data, True),
                'Gears': self.format_items(stocks_data.get('lastSeen', {}).get('Gears', []), image_data, True),
                'Weather': self.format_items(stocks_data.get('lastSeen', {}).get('Weather', []), image_data, True),
                'Eggs': self.format_items(stocks_data.get('lastSeen', {}).get('Eggs', []), image_data, True),
                'Honey': self.format_items(stocks_data.get('lastSeen', {}).get('Honey', []), image_data, True)
            },
            
            'restockTimers': stocks_data.get('restockTimers', {})
        }
        
        # Сохраняем отформатированные данные для отладки
        try:
            with open('debug_stock_formatted.json', 'w', encoding='utf-8') as f:
                json.dump(formatted, f, indent=2, ensure_ascii=False)
            logger.info("💾 Отформатированные данные сохранены в debug_stock_formatted.json")
        except:
            pass
            
        return formatted

    def parse_formatted_stock_data(self, formatted_data):
        """Парсит отформатированные данные стока"""
        stock_items = {}
        
        try:
            logger.info(f"🔍 Начинаем парсинг отформатированных данных")
            
            # Основные категории стоков
            stock_categories = [
                'easterStock',      # Пасхальный сток
                'gearStock',        # Инструменты
                'eggStock',         # Яйца
                'nightStock',       # Ночной магазин
                'honeyStock',       # Мед
                'cosmeticsStock',   # Косметика
                'seedsStock'        # Семена
            ]
            
            total_found = 0
            
            for category in stock_categories:
                if category in formatted_data and isinstance(formatted_data[category], list):
                    category_items = formatted_data[category]
                    logger.info(f"📦 Обрабатываем категорию {category}: {len(category_items)} предметов")
                    
                    category_found = 0
                    for item in category_items:
                        try:
                            if not isinstance(item, dict):
                                continue
                                
                            # Получаем название предмета
                            name = item.get('name')
                            if not name:
                                continue
                                
                            name = str(name).lower().strip()
                            
                            # Получаем количество (value в отформатированных данных)
                            quantity = item.get('value')
                            if quantity is None:
                                continue
                                
                            if isinstance(quantity, str):
                                try:
                                    quantity = int(quantity)
                                except ValueError:
                                    quantity = 0
                            elif isinstance(quantity, (int, float)):
                                quantity = int(quantity)
                            else:
                                quantity = 0
                            
                            # Проверяем, отслеживается ли предмет и есть ли в наличии
                            if name in self.proctor_items and quantity > 0:
                                stock_items[name] = quantity
                                category_found += 1
                                total_found += 1
                                logger.info(f"🎯 Найден в {category}: {name} - {quantity} шт.")
                                
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка обработки элемента в {category}: {e}")
                            continue
                    
                    logger.info(f"✅ В категории {category} найдено {category_found} отслеживаемых предметов")
            
            logger.info(f"📊 ИТОГО: Найдено {total_found} отслеживаемых предметов во всех категориях")
            
            # Логируем все доступные категории для отладки
            logger.info(f"🔍 Доступные категории в данных: {list(formatted_data.keys())}")
            for category in stock_categories:
                if category in formatted_data:
                    items_count = len(formatted_data[category])
                    logger.info(f"   {category}: {items_count} предметов")
            
            return stock_items
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга отформатированных данных: {e}")
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
            display_name = item_name.title()
            items_text += f"🟢 *{display_name}* — `{quantity}` шт.\n"
        
        message = f"{title}{items_text}\n⏰ *Обновлено:* {datetime.now().strftime('%H:%M:%S')}\n\n🔔 *Garden Stock Bot*"
        return message

    def find_new_items(self, current_stock):
        """Находит новые предметы по сравнению с предыдущей проверкой"""
        new_items = {}
        
        logger.info(f"🔍 Поиск новых предметов. Текущий сток: {len(current_stock)} предметов")
        logger.info(f"📋 Текущие предметы: {list(current_stock.keys())}")
        logger.info(f"📋 Предыдущий сток: {list(self.last_stock.keys())}")
        
        for item_name, quantity in current_stock.items():
            if item_name not in self.last_stock:
                new_items[item_name] = quantity
                logger.info(f"🆕 НОВЫЙ ПРЕДМЕТ ОБНАРУЖЕН: {item_name} - {quantity} шт.")
            else:
                logger.info(f"🔁 Предмет уже был: {item_name} - {quantity} шт.")
                
        self.last_stock = current_stock.copy()
        
        logger.info(f"🎯 ИТОГО новых предметов: {len(new_items)}")
        return new_items

    async def send_stock_updates(self, application, new_items):
        """Отправляет обновления во все одобренные каналы"""
        if not new_items:
            logger.info("ℹ️ Нет новых предметов для отправки")
            return
            
        message = self.format_stock_message(new_items)
        if not message:
            logger.warning("⚠️ Не удалось сформировать сообщение")
            return
            
        sent_count = 0
        failed_channels = []
        
        logger.info(f"📨 Начинаем отправку в {len(self.approved_channels)} каналов")
        
        for channel_id, channel_info in list(self.approved_channels.items()):
            try:
                logger.info(f"🔄 Пытаемся отправить в канал: {channel_info['title']} (ID: {channel_id})")
                
                # Отправляем основное сообщение
                sent_message = await application.bot.send_message(
                    chat_id=channel_id, 
                    text=message, 
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                
                self.last_messages[str(channel_id)] = sent_message.message_id
                sent_count += 1
                
                logger.info(f"✅ Сообщение отправлено в канал {channel_info['title']}")
                await asyncio.sleep(2)  # Задержка между отправками
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Ошибка отправки в канал {channel_id}: {error_msg}")
                
                # Проверяем тип ошибки
                if any(err in error_msg for err in ["Chat not found", "bot is not a member", "Forbidden", "unauthorized"]):
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
        """Основной цикл проверки стока с настраиваемым интервалом"""
        logger.info("🔄 Запущен цикл проверки стока")
        
        check_count = 0
        error_count = 0
        
        while True:
            try:
                current_interval = getattr(self, 'check_interval', 30)
                logger.info(f"🔍 Проверка стока #{check_count + 1} (интервал: {current_interval}сек)")
                
                current_stock = await self.get_real_garden_stock()
                
                if current_stock:
                    logger.info(f"📊 Получен сток: {len(current_stock)} предметов")
                    
                    # Детальное логирование всех предметов
                    if current_stock:
                        logger.info("📝 ДЕТАЛЬНЫЙ ОТЧЕТ О СТОКЕ:")
                        for item_name, quantity in current_stock.items():
                            status = "🎯 ОТСЛЕЖИВАЕТСЯ" if item_name in self.proctor_items else "👀 В стоке"
                            logger.info(f"  {status}: {item_name} - {quantity} шт.")
                    
                    new_items = self.find_new_items(current_stock)
                    
                    if new_items:
                        logger.info(f"🎁 Найдены новые предметы: {list(new_items.keys())}")
                        logger.info(f"📨 Начинаю отправку в {len(self.approved_channels)} каналов")
                        await self.send_stock_updates(application, new_items)
                        error_count = 0
                    else:
                        check_count += 1
                        logger.info(f"🔍 Проверка #{check_count} - новых предметов нет")
                        
                        # Логируем каждые 5 проверок
                        if check_count % 5 == 0:
                            tracked_in_stock = [item for item in self.proctor_items if item in current_stock]
                            logger.info(f"📈 Статистика: В стоке отслеживаемых: {len(tracked_in_stock)}/{len(self.proctor_items)}")
                            
                else:
                    logger.warning("⚠️ Не удалось получить данные стока")
                    error_count += 1
                    if error_count > 3:
                        logger.error("🔄 Перезапускаем цикл проверки из-за множественных ошибок")
                        # Сбрасываем last_stock при перезапуске
                        self.last_stock = {}
                        return await self.check_stock_loop(application)
                
                # Используем настраиваемый интервал
                await asyncio.sleep(current_interval)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле проверки: {e}")
                error_count += 1
                await asyncio.sleep(60)

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
⏰ Интервал проверки: {getattr(self, 'check_interval', 30)} сек.

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
    
    if not bot.is_whitelisted(user_id):
        welcome_text = f"""
🌿 Добро пожаловать, {user.first_name}! 🌿

🤖 *Garden Stock Bot* - автоматический отслеживатель стока предметов в игре *Grow A Garden*.

✨ *Функции:*
• Автоматическая проверка стока
• Уведомления о новых предметах  
• Работа 24/7

📝 *Подключить канал:* /request

❓ *Помощь:* Нажмите кнопку ниже
        """
        keyboard = [
            [InlineKeyboardButton("📋 Подать заявку", callback_data="make_request")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help_public")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        return
        
    # Для администратора - ПОЛНЫЙ СПИСОК КОМАНД
    admin_welcome = f"""
🌟 Добро пожаловать, администратор {user.first_name}! 🌟

🤖 *Garden Stock Bot* готов к работе!

📊 *Текущая статистика:*
• Каналов одобрено: {len(bot.approved_channels)}
• Предметов отслеживается: {len(bot.proctor_items)}
• Заявок на рассмотрении: {len(bot.pending_channels)}
• Интервал проверки: {getattr(bot, 'check_interval', 30)} сек.

🛠 *ПОЛНЫЙ СПИСОК КОМАНД:*

📈 *Информация:*
/stats - Подробная статистика
/channels - Одобренные каналы  
/pending - Заявки на одобрение
/proctor - Отслеживаемые предметы

⚙️ *Управление каналами:*
/approve <ID> - Одобрить канал
/reject <ID> - Отклонить канал

👥 *Управление администраторами:*
/addadmin <ID> - Добавить админа
/removeadmin <ID> - Удалить админа
/listadmins - Список админов

🎯 *Управление предметами:*
/additem <название> - Добавить предмет
/removeitem <название> - Удалить предмет
/setinterval <секунды> - Интервал проверки

🧪 *Тестовые команды:*
/teststock - Тест проверки стока
/testmessage <ID> - Тест отправки сообщения
/resetstock - Сбросить память о стоке

❓ *Помощь:*
/help - Полный список команд

💡 *Бот уже работает и отслеживает сток каждые {getattr(bot, 'check_interval', 30)} секунд!*
    """
    
    stats = bot.get_bot_stats()
    await update.message.reply_text(admin_welcome)
    await update.message.reply_text(stats)

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для подачи заявки на подключение канала"""
    user = update.effective_user
    
    instruction_text = f"""
📨 ЗАЯВКА НА ПОДКЛЮЧЕНИЕ КАНАЛА

👤 *Заявитель:* {user.first_name}
🆔 *ID:* `{user.id}`

📝 *Инструкция:*

1. *Добавьте бота в канал* как администратора с правами:
   - ✅ Отправка сообщений
   - ✅ Удаление сообщений

2. *Пришлите данные канала:*
   - Название канала
   - ID канала (если известен)  
   - Ссылка-приглашение

3. *Формат:*

⏳ *Рассмотрение в течение 24 часов*
    """
    
    context.user_data['making_request'] = True
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel_request")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(instruction_text, reply_markup=reply_markup)

async def handle_request_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает данные заявки"""
    user = update.effective_user
    text = update.message.text
    
    if not context.user_data.get('making_request'):
        return
    
    # Парсим данные
    lines = text.split('\n')
    channel_data = {'name': '', 'id': '', 'link': ''}
    
    for line in lines:
        line = line.strip()
        if line.startswith('Название:'):
            channel_data['name'] = line.replace('Название:', '').strip()
        elif line.startswith('ID:'):
            channel_data['id'] = line.replace('ID:', '').strip()
        elif 't.me/' in line or 'https://' in line:
            channel_data['link'] = line.strip()
    
    if not channel_data['name']:
        await update.message.reply_text("❌ Укажите название канала: `Название: Ваше название`")
        return
    
    # Создаем заявку
    request_id = int(time.time())
    channel_id = channel_data['id'] or f"pending_{request_id}"
    invited_by = f"{user.first_name} (ID: {user.id})"
    
    if bot.add_pending_channel(channel_id, channel_data['name'], invited_by, channel_data['link']):
        context.user_data.pop('making_request', None)
        
        success_text = f"""
✅ ЗАЯВКА ПОДАНА!

📋 *Данные:*
• Название: {channel_data['name']}
• ID: `{channel_id}`
• Ссылка: {channel_data['link'] or 'Не указана'}

⏳ *Ожидайте рассмотрения администраторами.*
        """
        
        await update.message.reply_text(success_text)
        
        # Уведомляем администраторов
        notification_text = f"""
📨 НОВАЯ ЗАЯВКА!

📢 {channel_data['name']}
🆔 `{channel_id}`
👤 {user.first_name} (`{user.id}`)

/pending - для рассмотрения
        """
        
        for admin_id in bot.whitelist:
            try:
                await context.bot.send_message(int(admin_id), notification_text)
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить {admin_id}: {e}")
                
    else:
        await update.message.reply_text("❌ Ошибка при создании заявки.")

async def cancel_request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет заполнение заявки"""
    if context.user_data.get('making_request'):
        context.user_data.pop('making_request', None)
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
        await update.message.reply_text("❌ Нет доступа.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /approve <channel_id>")
        return
        
    channel_id = context.args[0]
    
    if channel_id not in bot.pending_channels:
        await update.message.reply_text("❌ Канал не найден в ожидании.")
        return
        
    channel_info = bot.pending_channels[channel_id]
    
    # Пробуем присоединиться к каналу если есть ссылка
    if channel_info.get('invite_link'):
        try:
            await context.bot.join_chat(channel_info['invite_link'])
            logger.info(f"✅ Бот присоединился к каналу {channel_info['title']}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось присоединиться: {e}")
            await update.message.reply_text(f"⚠️ Не удалось присоединиться к каналу: {e}")
    
    if bot.add_approved_channel(channel_id, channel_info['title'], f"user_{user_id}"):
        bot.remove_pending_channel(channel_id)
        
        # Отправляем тестовое сообщение в канал
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text="✅ *Garden Stock Bot подключен!*\n\n🔔 Теперь вы будете получать уведомления о новых предметах в стоке игры Grow A Garden!",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Тестовое сообщение отправлено в {channel_info['title']}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить тестовое сообщение: {e}")
        
        await update.message.reply_text(f"✅ Канал одобрен!\n\n📢 {channel_info['title']}\n🆔 `{channel_id}`")
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

async def proctor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие отслеживаемые предметы"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    items_text = "🎯 ОТСЛЕЖИВАЕМЫЕ ПРЕДМЕТЫ:\n\n"
    for i, item in enumerate(bot.proctor_items, 1):
        items_text += f"{i}. `{item}`\n"
    
    items_text += f"\n📊 Всего предметов: {len(bot.proctor_items)}"
    items_text += f"\n⏰ Интервал проверки: {getattr(bot, 'check_interval', 30)} сек."
    
    await update.message.reply_text(items_text)

async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет предмет для отслеживания"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /additem <название предмета>")
        return
        
    item_name = ' '.join(context.args).lower().strip()
    
    if item_name in bot.proctor_items:
        await update.message.reply_text(f"❌ Предмет `{item_name}` уже отслеживается.")
        return
        
    bot.proctor_items.append(item_name)
    
    if bot.save_proctor_items():
        await update.message.reply_text(f"✅ Предмет `{item_name}` добавлен для отслеживания!")
        logger.info(f"✅ Добавлен предмет для отслеживания: {item_name}")
    else:
        await update.message.reply_text("❌ Ошибка при сохранении предмета.")

async def remove_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет предмет из отслеживания"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /removeitem <название предмета>")
        return
        
    item_name = ' '.join(context.args).lower().strip()
    
    if item_name not in bot.proctor_items:
        await update.message.reply_text(f"❌ Предмет `{item_name}` не найден в списке отслеживания.")
        return
        
    bot.proctor_items.remove(item_name)
    
    if bot.save_proctor_items():
        await update.message.reply_text(f"✅ Предмет `{item_name}` удален из отслеживания!")
        logger.info(f"✅ Удален предмет из отслеживания: {item_name}")
    else:
        await update.message.reply_text("❌ Ошибка при удалении предмета.")

async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает интервал проверки стока"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Использование: /setinterval <секунды>")
        return
        
    interval = int(context.args[0])
    
    if interval < 10:
        await update.message.reply_text("❌ Интервал не может быть меньше 10 секунд.")
        return
        
    if interval > 300:
        await update.message.reply_text("❌ Интервал не может быть больше 300 секунд.")
        return
        
    bot.check_interval = interval
    bot.save_proctor_items()
    
    await update.message.reply_text(f"✅ Интервал проверки установлен: {interval} секунд")
    logger.info(f"⏰ Установлен интервал проверки: {interval} сек.")

async def test_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для проверки стока"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    await update.message.reply_text("🔍 Запускаю тестовую проверку стока...")
    
    current_stock = await bot.get_real_garden_stock()
    
    if current_stock:
        stock_text = "📊 ТЕКУЩИЙ СТОК:\n\n"
        for item_name, quantity in current_stock.items():
            status = "🎯" if item_name in bot.proctor_items else "👀"
            stock_text += f"{status} `{item_name}` - {quantity} шт.\n"
        
        tracked_count = len([item for item in bot.proctor_items if item in current_stock])
        stock_text += f"\n📈 Отслеживаемых в стоке: {tracked_count}/{len(bot.proctor_items)}"
        
        await update.message.reply_text(stock_text)
    else:
        await update.message.reply_text("❌ Не удалось получить данные стока")

async def test_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для отправки сообщения"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Использование: /testmessage <channel_id>")
        return
        
    channel_id = context.args[0]
    
    try:
        test_message = "🧪 *ТЕСТОВОЕ СООБЩЕНИЕ*\n\nЭто тестовая отправка от Garden Stock Bot. Если вы видите это сообщение, бот работает корректно!"
        
        await context.bot.send_message(
            chat_id=channel_id,
            text=test_message,
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(f"✅ Тестовое сообщение отправлено в канал `{channel_id}`")
        logger.info(f"✅ Тестовое сообщение отправлено в {channel_id}")
        
    except Exception as e:
        error_msg = f"❌ Ошибка отправки тестового сообщения: {e}"
        await update.message.reply_text(error_msg)
        logger.error(error_msg)

async def reset_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает память о предыдущем стоке"""
    user_id = update.effective_user.id
    
    if not bot.is_whitelisted(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
        
    bot.last_stock = {}
    await update.message.reply_text("✅ Память о предыдущем стоке сброшена! Следующая проверка покажет все предметы как новые.")
    logger.info("🔄 Память о стоке сброшена администратором")

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
        
    # Помощь для администраторов - ПОЛНЫЙ СПИСОК
    help_text = """
🌿 GARDEN STOCK BOT - ПОЛНЫЙ СПИСОК КОМАНД 🌿

📊 ИНФОРМАЦИЯ:
/start - Главное меню
/stats - Статистика бота
/channels - Одобренные каналы
/pending - Заявки на рассмотрение
/proctor - Отслеживаемые предметы

⚙️ УПРАВЛЕНИЕ КАНАЛАМИ:
/approve <ID> - Одобрить канал
/reject <ID> - Отклонить канал

👥 УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ:
/addadmin <ID> - Добавить администратора
/removeadmin <ID> - Удалить администратора
/listadmins - Список администраторов

🎯 УПРАВЛЕНИЕ ПРЕДМЕТАМИ:
/additem <название> - Добавить предмет для отслеживания
/removeitem <название> - Удалить предмет из отслеживания
/setinterval <секунды> - Установить интервал проверки

🧪 ТЕСТОВЫЕ КОМАНДЫ:
/teststock - Проверить текущий сток
/testmessage <ID> - Отправить тестовое сообщение
/resetstock - Сбросить память о стоке

📝 ПРОЦЕСС ПОДКЛЮЧЕНИЯ:
1. Пользователь использует /request
2. Заполняет форму заявки
3. Администратор проверяет заявки через /pending
4. Одобряет/отклоняет через кнопки или команды

💡 Бот автоматически отслеживает сток!
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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    await query.answer()
    
    if data == "make_request":
        await query.message.reply_text("📝 Используйте /request для подачи заявки")
        return
        
    elif data == "help_public":
        help_text = """
❓ ПОМОЩЬ:

🤖 *Функции бота:*
- Отслеживает сток предметов в Grow A Garden
- Уведомляет о новых предметах
- Работает 24/7

📝 *Как подключить канал?*
- Используйте /request
- Следуйте инструкциям
- Ожидайте одобрения

⏰ *Проверка стока:* каждые 30 секунд
        """
        await query.message.reply_text(help_text)
        return
        
    elif data == "cancel_request":
        if context.user_data.get('making_request'):
            context.user_data.pop('making_request', None)
            await query.message.edit_text("❌ Заявка отменена.")
        return
    
    # Проверяем права для административных действий
    if not bot.is_whitelisted(user.id):
        await query.answer("❌ Нет доступа!", show_alert=True)
        return
        
    if data.startswith('approve:'):
        channel_id = data.split(':')[1]
        
        if channel_id in bot.pending_channels:
            channel_info = bot.pending_channels[channel_id]
            
            # Пробуем присоединиться к каналу
            if channel_info.get('invite_link'):
                try:
                    await context.bot.join_chat(channel_info['invite_link'])
                    logger.info(f"✅ Бот присоединился к {channel_info['title']}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось присоединиться: {e}")
            
            if bot.add_approved_channel(channel_id, channel_info['title'], f"user_{user.id}"):
                bot.remove_pending_channel(channel_id)
                
                # Отправляем тестовое сообщение
                try:
                    await context.bot.send_message(
                        chat_id=channel_id,
                        text="✅ *Garden Stock Bot подключен!*\n\nОжидайте уведомлений о новых предметах!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить тестовое сообщение: {e}")
                
                await query.edit_message_text(
                    f"✅ Канал одобрен!\n\n"
                    f"📢 {channel_info['title']}\n"
                    f"🆔 `{channel_id}`"
                )
            else:
                await query.edit_message_text("❌ Ошибка при одобрении.")
        else:
            await query.edit_message_text("❌ Канал не найден!")
            
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
                await query.edit_message_text("❌ Ошибка при отклонении.")
        else:
            await query.edit_message_text("❌ Канал не найден!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}", exc_info=context.error)

def setup_handlers(application):
    """Настраивает обработчики команд"""
    # Основные команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("request", request_command))
    application.add_handler(CommandHandler("cancelrequest", cancel_request_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("reject", reject_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Команды управления администраторами
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("removeadmin", remove_admin_command))
    application.add_handler(CommandHandler("listadmins", list_admins_command))
    
    # Новые команды управления предметами
    application.add_handler(CommandHandler("proctor", proctor_command))
    application.add_handler(CommandHandler("additem", add_item_command))
    application.add_handler(CommandHandler("removeitem", remove_item_command))
    application.add_handler(CommandHandler("setinterval", set_interval_command))
    
    # Тестовые команды
    application.add_handler(CommandHandler("teststock", test_stock_command))
    application.add_handler(CommandHandler("testmessage", test_message_command))
    application.add_handler(CommandHandler("resetstock", reset_stock_command))
    
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
        logger.info(f"   - Интервал проверки: {getattr(bot, 'check_interval', 30)} сек.")
        
        # Запускаем polling
        application.run_polling()
        
    except ImportError:
        logger.error("❌ Файл config.py не найден! Создайте его с BOT_TOKEN.")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")

if __name__ == '__main__':
    main()