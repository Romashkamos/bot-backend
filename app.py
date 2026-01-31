from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с фронтенда

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8402586959:AAGRTEGtSy7KoUlJDZvaNSxL3JKuZPWUMrY')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '123')

# ===================== БАЗА ДАННЫХ =====================
def get_db():
    conn = sqlite3.connect('bot_data.db')
    conn.row_factory = sqlite3.Row  # Чтобы получать данные как словарь
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            refs INTEGER DEFAULT 0,
            last_update TEXT,
            total_earned REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица транзакций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            type TEXT,
            description TEXT,
            admin TEXT DEFAULT 'System',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            amount REAL,
            is_used INTEGER DEFAULT 0,
            created_at TEXT,
            used_by INTEGER DEFAULT NULL,
            used_at TEXT DEFAULT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

# Инициализируем БД при запуске
init_db()

# ===================== АУТЕНТИФИКАЦИЯ =====================
def check_auth(headers):
    """Проверяем авторизацию"""
    # В реальном проекте используй JWT токены
    auth_token = headers.get('X-Auth-Token')
    return auth_token == 'demo_token'

# ===================== API ДЛЯ ФРОНТЕНДА =====================
@app.route('/api/login', methods=['POST'])
def login():
    """Вход в панель управления"""
    data = request.json
    
    if (data.get('username') == ADMIN_USERNAME and 
        data.get('password') == ADMIN_PASSWORD):
        return jsonify({
            'success': True,
            'token': 'demo_token',
            'user': {
                'username': ADMIN_USERNAME,
                'name': 'Администратор'
            }
        })
    
    return jsonify({'success': False, 'error': 'Неверные данные'})

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """Получить статистику для дашборда"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM promo_codes WHERE is_used = 0")
    active_codes = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'stats': {
            'totalUsers': total_users,
            'totalBalance': total_balance,
            'activeCodes': active_codes,
            'activeToday': total_users  # Для демо
        }
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    """Получить список пользователей"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    
    # Преобразуем в список словарей
    users_list = []
    for user in users:
        users_list.append(dict(user))
    
    conn.close()
    
    return jsonify({'users': users_list})

@app.route('/api/user/add', methods=['POST'])
def add_user():
    """Добавить нового пользователя"""
    if not check_auth(request.headers):
        return jsonify({'success': False, 'error': 'Нет доступа'})
    
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, balance, last_update)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data.get('telegram_id'),
            data.get('username'),
            data.get('first_name'),
            data.get('balance', 0),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        ))
        
        conn.commit()
        user_id = cursor.lastrowid
        
        # Если указан баланс, добавляем транзакцию
        if data.get('balance', 0) > 0:
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description, admin)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                data.get('telegram_id'),
                data.get('balance', 0),
                'deposit',
                'Начальный баланс',
                'Admin'
            ))
            conn.commit()
        
        conn.close()
        
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user/balance', methods=['POST'])
def update_balance():
    """Изменить баланс пользователя"""
    if not check_auth(request.headers):
        return jsonify({'success': False, 'error': 'Нет доступа'})
    
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Обновляем баланс
        cursor.execute('''
            UPDATE users 
            SET balance = balance + ?, 
                last_update = ?,
                total_earned = total_earned + ?
            WHERE telegram_id = ?
        ''', (
            data['amount'],
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            max(data['amount'], 0),  # Добавляем только положительные суммы к total_earned
            data['user_id']
        ))
        
        # Добавляем транзакцию
        transaction_type = 'deposit' if data['amount'] > 0 else 'withdrawal'
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description, admin)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['user_id'],
            data['amount'],
            transaction_type,
            data.get('description', 'Изменение администратором'),
            'Admin'
        ))
        
        conn.commit()
        
        # Получаем новый баланс
        cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (data['user_id'],))
        new_balance = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({'success': True, 'new_balance': new_balance})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/message/send', methods=['POST'])
def send_message():
    """Отправить сообщение через бота"""
    if not check_auth(request.headers):
        return jsonify({'success': False, 'error': 'Нет доступа'})
    
    data = request.json
    
    try:
        # Отправляем сообщение через Telegram API
        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={
                'chat_id': data['chat_id'],
                'text': data['text'],
                'parse_mode': data.get('parse_mode', 'HTML')
            }
        )
        
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ===================== API ДЛЯ ТЕЛЕГРАМ БОТА =====================
@app.route('/api/bot/user/<int:telegram_id>', methods=['GET'])
def get_bot_user(telegram_id):
    """Получить данные пользователя для бота"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    
    conn.close()
    
    if user:
        return jsonify({
            'exists': True,
            'balance': user['balance'],
            'first_name': user['first_name'],
            'last_update': user['last_update'],
            'refs': user['refs']
        })
    
    return jsonify({'exists': False})

@app.route('/api/bot/user/create', methods=['POST'])
def create_bot_user():
    """Создать пользователя из бота"""
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли пользователь
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (data['telegram_id'],))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': True, 'message': 'Пользователь уже существует'})
        
        # Создаем нового пользователя
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, last_update)
            VALUES (?, ?, ?, ?)
        ''', (
            data['telegram_id'],
            data.get('username'),
            data.get('first_name'),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Пользователь создан'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/bot/code/check', methods=['POST'])
def check_promo_code():
    """Проверить промокод"""
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM promo_codes WHERE code = ? AND is_used = 0", (data['code'],))
    code_data = cursor.fetchone()
    
    if not code_data:
        conn.close()
        return jsonify({'valid': False, 'error': 'Код не найден или уже использован'})
    
    return jsonify({
        'valid': True,
        'amount': code_data['amount'],
        'code': code_data['code']
    })

@app.route('/api/bot/code/use', methods=['POST'])
def use_promo_code():
    """Использовать промокод"""
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Проверяем код
        cursor.execute("SELECT * FROM promo_codes WHERE code = ? AND is_used = 0", (data['code'],))
        code_data = cursor.fetchone()
        
        if not code_data:
            conn.close()
            return jsonify({'success': False, 'error': 'Код не найден'})
        
        # Обновляем код как использованный
        cursor.execute('''
            UPDATE promo_codes 
            SET is_used = 1, used_by = ?, used_at = ?
            WHERE code = ?
        ''', (data['user_id'], datetime.now().strftime("%d.%m.%Y %H:%M"), data['code']))
        
        # Обновляем баланс пользователя
        cursor.execute('''
            UPDATE users 
            SET balance = balance + ?,
                last_update = ?,
                total_earned = total_earned + ?
            WHERE telegram_id = ?
        ''', (
            code_data['amount'],
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            code_data['amount'],
            data['user_id']
        ))
        
        # Добавляем транзакцию
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (
            data['user_id'],
            code_data['amount'],
            'promo',
            f'Активация промокода {data["code"]}'
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'amount': code_data['amount']})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

# ===================== ЗАПУСК =====================
if __name__ == '__main__':
    # Получаем порт из переменных окружения (нужно для хостингов)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
