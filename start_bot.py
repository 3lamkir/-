#!/usr/bin/env python3
"""
Garden Stock Bot - Запускной файл
Автоматически создает необходимые файлы и запускает бота
"""

import os
import sys
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_files():
    """Проверяет наличие необходимых файлов"""
    required_files = ['config.py', 'proctor.txt']
    
    for file in required_files:
        if not os.path.exists(file):
            logger.warning(f"⚠️ Файл {file} не найден!")
            return False
    
    return True

def create_config():
    """Создает файл конфигурации если его нет"""
    if not os.path.exists('config.py'):
        logger.info("📝 Создаю файл config.py...")
        with open('config.py', 'w', encoding='utf-8') as f:
            f.write('''# Конфигурация бота
# Получите токен у @BotFather в Telegram

BOT_TOKEN = "ВСТАВЬТЕ_ВАШ_ТОКЕН_ЗДЕСЬ"

# Пример: BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
''')
        logger.info("✅ Файл config.py создан!")

def create_proctor():
    """Создает файл proctor.txt если его нет"""
    if not os.path.exists('proctor.txt'):
        logger.info("📝 Создаю файл proctor.txt...")
        with open('proctor.txt', 'w', encoding='utf-8') as f:
            f.write('''# Список предметов для отслеживания
# Каждый предмет на новой строке в нижнем регистре

corn
cacao
tomato
carrot
potato
onion
pumpkin
''')
        logger.info("✅ Файл proctor.txt создан!")

def install_requirements():
    """Устанавливает зависимости"""
    logger.info("📦 Проверяем зависимости...")
    try:
        import telegram
        import aiohttp
        logger.info("✅ Все зависимости установлены!")
    except ImportError as e:
        logger.error(f"❌ Не все зависимости установлены: {e}")
        logger.info("🔄 Устанавливаем зависимости...")
        os.system("pip install -r requirements.txt")

def main():
    """Основная функция запуска"""
    logger.info("🌿 Запускаем Garden Stock Bot...")
    
    # Устанавливаем зависимости
    install_requirements()
    
    # Создаем необходимые файлы
    create_config()
    create_proctor()
    
    # Проверяем конфигурацию
    try:
        from config import BOT_TOKEN
        if BOT_TOKEN == "ВСТАВЬТЕ_ВАШ_ТОКЕН_ЗДЕСЬ" or BOT_TOKEN == "":
            logger.error("❌ Токен бота не настроен!")
            logger.info("📝 Откройте файл config.py и замените BOT_TOKEN на ваш токен от @BotFather")
            return
    except ImportError:
        logger.error("❌ Файл config.py не найден!")
        return
    
    # Запускаем бота
    try:
        from main import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()