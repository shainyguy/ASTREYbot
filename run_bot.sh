#!/bin/bash

echo "🚀 Запуск Telegram-бота воронки продаж для Astrey.ru"
echo "====================================================="

# Проверка наличия Python 3
if ! command -v python3 &> /dev/null
then
    echo "❌ Ошибка: Python 3 не установлен! Пожалуйста, установите Python 3."
    exit 1
fi

# Проверка и установка виртуального окружения
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения venv..."
    python3 -m venv venv
fi

# Активация виртуального окружения
source venv/bin/activate

# Обновление pip и установка зависимостей
echo "📥 Установка и обновление зависимостей из requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# Проверка, задан ли токен
if grep -q "YOUR_TELEGRAM_BOT_TOKEN_HERE" config.py; then
    echo ""
    echo "🔑 Кажется, вы не указали токен бота в файле config.py."
    echo "Введите ваш Telegram Bot Token (от @BotFather):"
    read -r BOT_TOKEN
    
    if [ -z "$BOT_TOKEN" ]; then
        echo "❌ Токен не введен. Запуск невозможен."
        exit 1
    fi
    
    # Замена заглушки токена на реальный токен в config.py
    sed -i "s/YOUR_TELEGRAM_BOT_TOKEN_HERE/$BOT_TOKEN/g" config.py
    echo "✅ Токен успешно сохранен в config.py!"
fi

echo "🚀 Запуск бота..."
python3 bot.py
