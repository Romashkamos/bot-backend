import telebot
import requests
from telebot import types
import sqlite3
import os
from datetime import datetime

# Конфигурация
TOKEN = '8402586959:AAGRTEGtSy7KoUlJDZvaNSxL3JKuZPWUMrY'
BACKEND_URL = 'https://bot-backend-production-14a7.up.railway.app'
ADMIN_ID = 7501734808  # Замени на свой Telegram ID (узнай через @userinfobot)

bot = telebot.TeleBot(TOKEN)

# ===================== БАЗА ДАННЫХ ДЛЯ БОТА =====================
def init_bot_db():
    conn = sqlite3.connect('bot_local.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            daily_bonus_claimed DATE DEFAULT NULL,
            referral_code TEXT UNIQUE,
            referred_by INTEGER DEFAULT NULL,
            notifications_enabled BOOLEAN DEFAULT 1,
            language TEXT DEFAULT 'ru'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            direction TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_bot_db()

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def get_user_from_backend(user_id):
    """Получить данные пользователя из бэкенда"""
    try:
        response = requests.get(f'{BACKEND_URL}/api/bot/user/{user_id}')
        return response.json()
    except:
        return {'exists': False}

def create_user_in_backend(user_id, username, first_name):
    """Создать пользователя в бэкенде"""
    try:
        response = requests.post(f'{BACKEND_URL}/api/bot/user/create', json={
            'telegram_id': user_id,
            'username': username,
            'first_name': first_name
        })
        return response.json()
    except:
        return {'success': False}

def update_balance_in_backend(user_id, amount, description=''):
    """Обновить баланс в бэкенде"""
    try:
        response = requests.post(f'{BACKEND_URL}/api/user/balance', json={
            'user_id': user_id,
            'amount': amount,
            'description': description
        })
        return response.json()
    except:
        return {'success': False}

def check_promo_code(code, user_id):
    """Проверить промокод"""
    try:
        response = requests.post(f'{BACKEND_URL}/api/bot/code/check', json={
            'code': code,
            'user_id': user_id
        })
        return response.json()
    except:
        return {'valid': False}

def use_promo_code(code, user_id):
    """Использовать промокод"""
    try:
        response = requests.post(f'{BACKEND_URL}/api/bot/code/use', json={
            'code': code,
            'user_id': user_id
        })
        return response.json()
    except:
        return {'success': False}

# ===================== КОМАНДЫ БОТА =====================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Проверяем или создаем пользователя
    user_data = get_user_from_backend(user_id)
    
    if not user_data.get('exists'):
        # Создаем нового пользователя
        create_user_in_backend(user_id, username, first_name)
        user_data = get_user_from_backend(user_id)
    
    # Создаем клавиатуру
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton('💰 Баланс')
    btn2 = types.KeyboardButton('🎁 Промокод')
    btn3 = types.KeyboardButton('👥 Рефералы')
    btn4 = types.KeyboardButton('📊 Статистика')
    btn5 = types.KeyboardButton('🆘 Помощь')
    markup.add(btn1, btn2, btn3, btn4, btn5)
    
    # Приветственное сообщение
    welcome_text = f"""
🎉 *Добро пожаловать, {first_name}!*

🤖 *Я — бот для управления балансами*
💰 *Ваш текущий баланс:* ${user_data.get('balance', 0)}

📋 *Доступные команды:*
/start - Главное меню
/balance - Проверить баланс
/promo - Активировать промокод
/referral - Реферальная система
/stats - Ваша статистика
/help - Помощь по боту

👇 *Или используйте кнопки ниже:*
"""
    
    bot.send_message(
        user_id, 
        welcome_text,
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    # Отправляем ежедневный бонус
    give_daily_bonus(user_id)

@bot.message_handler(commands=['balance'])
def balance_command(message):
    user_id = message.from_user.id
    user_data = get_user_from_backend(user_id)
    
    if user_data.get('exists'):
        balance = user_data.get('balance', 0)
        last_update = user_data.get('last_update', 'сегодня')
        
        response = f"""
💰 *ВАШ БАЛАНС*

💳 Основной счет: *${balance}*
📅 Обновлено: {last_update}

💸 *Минимальный вывод:* $50
📈 *Доступные действия:*
• Пополнить баланс
• Вывести средства
• Пригласить друзей
"""
        
        # Кнопки для пополнения/вывода
        markup = types.InlineKeyboardMarkup()
        btn1 = types.InlineKeyboardButton('➕ Пополнить', callback_data='deposit')
        btn2 = types.InlineKeyboardButton('➖ Вывести', callback_data='withdraw')
        markup.add(btn1, btn2)
        
        bot.send_message(user_id, response, parse_mode='Markdown', reply_markup=markup)
    else:
        bot.send_message(user_id, "❌ Вы не зарегистрированы. Используйте /start")

@bot.message_handler(commands=['promo'])
def promo_command(message):
    user_id = message.from_user.id
    
    # Запрос промокода
    msg = bot.send_message(
        user_id,
        "🎁 *АКТИВАЦИЯ ПРОМОКОДА*\n\nВведите промокод:",
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(msg, process_promo_code)

def process_promo_code(message):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    # Проверяем промокод
    check_result = check_promo_code(code, user_id)
    
    if check_result.get('valid'):
        # Используем промокод
        use_result = use_promo_code(code, user_id)
        
        if use_result.get('success'):
            amount = use_result.get('amount', 0)
            bot.send_message(
                user_id,
                f"✅ *Промокод активирован!*\n\n🎁 Получено: *${amount}*\n💳 Новый баланс доступен по /balance",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(user_id, f"❌ Ошибка: {use_result.get('error', 'Неизвестная ошибка')}")
    else:
        bot.send_message(user_id, f"❌ Неверный промокод или он уже использован")

@bot.message_handler(commands=['referral'])
def referral_command(message):
    user_id = message.from_user.id
    user_data = get_user_from_backend(user_id)
    
    refs = user_data.get('refs', 0)
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    
    response = f"""
👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*

📊 Ваши рефералы: *{refs}*
💰 Заработано с рефералов: *${refs * 10}*

🔗 *Ваша реферальная ссылка:*
`{referral_link}`

🎯 *Как это работает:*
1. Делитесь ссылкой с друзьями
2. За каждого приглашенного получаете $10
3. Друг также получает $5 на старт
4. Выводите заработанное от $50

📈 *Ваша статистика:*
• Приглашено: {refs} человек
• Заработано: ${refs * 10}
• Доступно к выводу: ${refs * 10}
"""
    
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton('📤 Поделиться ссылкой', 
                                     url=f'https://t.me/share/url?url={referral_link}&text=Присоединяйся%20к%20лучшему%20боту!')
    markup.add(btn1)
    
    bot.send_message(user_id, response, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    user_id = message.from_user.id
    user_data = get_user_from_backend(user_id)
    
    if user_data.get('exists'):
        balance = user_data.get('balance', 0)
        refs = user_data.get('refs', 0)
        total_earned = user_data.get('total_earned', 0)
        
        response = f"""
📊 *ВАША СТАТИСТИКА*

👤 *Основное:*
• ID: `{user_id}`
• Баланс: *${balance}*
• Рефералов: *{refs}*
• Всего заработано: *${total_earned}*

🏆 *Достижения:*
{get_achievements(user_id, balance, refs)}

📈 *Прогресс:*
{get_progress_bar(balance, 1000)} До $1000
{get_progress_bar(refs, 10)} До 10 рефералов

🎯 *Цели:*
💰 $1000 на счету → Бонус $100
👥 10 рефералов → Бонус $50
"""
        
        bot.send_message(user_id, response, parse_mode='Markdown')
    else:
        bot.send_message(user_id, "❌ Вы не зарегистрированы. Используйте /start")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
🆘 *ПОМОЩЬ ПО БОТУ*

📋 *Основные команды:*
/start - Главное меню
/balance - Проверить баланс
/promo [КОД] - Активировать промокод
/referral - Реферальная система
/stats - Ваша статистика
/help - Эта справка

💰 *Пополнение баланса:*
1. Получите реквизиты у администратора
2. Сделайте перевод
3. Отправьте скриншот @admin

💸 *Вывод средств:*
• Минимальная сумма: $50
• Комиссия: 0%
• Время обработки: 1-24 часа

👥 *Реферальная система:*
• За каждого друга: $10 вам
• Друг получает: $5 на старт
• Вывод от $50

📞 *Поддержка:*
@admin - Администратор
@support - Техническая помощь

⚠️ *Правила:*
1. Запрещен спам
2. Одноразовые аккаунты блокируются
3. Вывод только на проверенные реквизиты
"""
    
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

# ===================== ОБРАБОТКА КНОПОК =====================
@bot.message_handler(func=lambda message: message.text == '💰 Баланс')
def balance_button(message):
    balance_command(message)

@bot.message_handler(func=lambda message: message.text == '🎁 Промокод')
def promo_button(message):
    promo_command(message)

@bot.message_handler(func=lambda message: message.text == '👥 Рефералы')
def referral_button(message):
    referral_command(message)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def stats_button(message):
    stats_command(message)

@bot.message_handler(func=lambda message: message.text == '🆘 Помощь')
def help_button(message):
    help_command(message)

# ===================== ОБРАБОТКА CALLBACK =====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    
    if call.data == 'deposit':
        # Пополнение баланса
        deposit_info = """
💳 *ПОПОЛНЕНИЕ БАЛАНСА*

📋 *Реквизиты для перевода:*
Карта: `2200 1234 5678 9010`
QIWI: `+7 (999) 123-45-67`
ЮMoney: `4100 1234 5678 9010`

📝 *Инструкция:*
1. Переведите нужную сумму
2. Сделайте скриншот перевода
3. Отправьте скриншот @admin
4. Ожидайте зачисления (1-60 минут)

⚠️ *Важно:*
• Минимальная сумма: $10
• Комиссия: 0% (наша)
• В комментарии укажите: {ваш ID}
"""
        bot.send_message(user_id, deposit_info, parse_mode='Markdown')
        
    elif call.data == 'withdraw':
        # Вывод средств
        user_data = get_user_from_backend(user_id)
        balance = user_data.get('balance', 0)
        
        if balance >= 50:
            withdraw_info = f"""
💸 *ВЫВОД СРЕДСТВ*

💰 Доступно: *${balance}*
💳 Минимум: *$50*

📋 *Для вывода:*
1. Напишите сумму (от $50 до ${balance})
2. Укажите реквизиты для получения
3. Подтвердите операцию

📞 *Отправьте запрос в формате:*
Вывод [сумма] [реквизиты]

*Пример:*
Вывод 100 2200****1234
"""
            bot.send_message(user_id, withdraw_info, parse_mode='Markdown')
        else:
            bot.send_message(
                user_id,
                f"❌ *Недостаточно средств*\n\nМинимум для вывода: $50\nВаш баланс: ${balance}",
                parse_mode='Markdown'
            )
    
    bot.answer_callback_query(call.id)

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def give_daily_bonus(user_id):
    """Выдать ежедневный бонус"""
    conn = sqlite3.connect('bot_local.db')
    cursor = conn.cursor()
    
    today = datetime.now().date().isoformat()
    
    cursor.execute(
        "SELECT daily_bonus_claimed FROM user_settings WHERE user_id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    
    if not result:
        # Первый бонус
        cursor.execute(
            "INSERT INTO user_settings (user_id, daily_bonus_claimed) VALUES (?, ?)",
            (user_id, today)
        )
        update_balance_in_backend(user_id, 5, 'Ежедневный бонус (первый)')
        bot.send_message(user_id, "🎁 *Первый ежедневный бонус!* +$5", parse_mode='Markdown')
    elif result[0] != today:
        # Ежедневный бонус
        cursor.execute(
            "UPDATE user_settings SET daily_bonus_claimed = ? WHERE user_id = ?",
            (today, user_id)
        )
        update_balance_in_backend(user_id, 2, 'Ежедневный бонус')
        bot.send_message(user_id, "🎁 *Ежедневный бонус!* +$2", parse_mode='Markdown')
    
    conn.commit()
    conn.close()

def get_achievements(user_id, balance, refs):
    """Получить достижения пользователя"""
    achievements = []
    
    if balance >= 100:
        achievements.append("💰 Баланс $100+")
    if balance >= 500:
        achievements.append("💰💰 Баланс $500+")
    if refs >= 5:
        achievements.append("👥 5 рефералов")
    if refs >= 10:
        achievements.append("👥👥 10 рефералов")
    
    if achievements:
        return "• " + "\n• ".join(achievements)
    return "• Нет достижений"

def get_progress_bar(current, target, length=10):
    """Получить строку прогресс-бара"""
    if target == 0:
        return "[" + " " * length + "] 0%"
    
    percent = min(current / target * 100, 100)
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {int(percent)}%"

# ===================== АДМИНИСТРАТИВНЫЕ КОМАНДЫ =====================
@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton('📊 Статистика', callback_data='admin_stats')
        btn2 = types.InlineKeyboardButton('👥 Пользователи', callback_data='admin_users')
        btn3 = types.InlineKeyboardButton('💰 Баланс', callback_data='admin_balance')
        btn4 = types.InlineKeyboardButton('📨 Рассылка', callback_data='admin_broadcast')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(
            user_id,
            "⚙️ *ПАНЕЛЬ АДМИНИСТРАТОРА*",
            parse_mode='Markdown',
            reply_markup=markup
        )
    else:
        bot.send_message(user_id, "❌ Доступ запрещен")

# ===================== ЗАПУСК БОТА =====================
print("🤖 Бот запущен...")
print(f"👤 Username: @{bot.get_me().username}")
print(f"🆔 ID: {bot.get_me().id}")
print("⌛ Ожидаю сообщений...")

bot.polling(none_stop=True)
