from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import time

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с фронтенда

# ===================== БАЗА ДАННЫХ =====================
def get_db():
    conn = sqlite3.connect('bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ===================== API =====================
@app.route('/')
def home():
    return jsonify({'status': 'ok', 'service': 'Telegram Bot Backend'})

@app.route('/api/login', methods=['POST'])
def login():
    """Вход в систему"""
    data = request.json
    
    # Проверяем логин и пароль
    if (data.get('username') == 'admin' and 
        data.get('password') == '123'):
        
        return jsonify({
            'success': True,
            'token': 'admin_token_' + str(int(time.time())),
            'user': {
                'username': 'admin',
                'name': 'Администратор',
                'role': 'admin'
            }
        })
    
    return jsonify({
        'success': False,
        'error': 'Неверный логин или пароль'
    })

@app.route('/api/stats', methods=['GET'])
def stats():
    """Статистика для дашборда"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return jsonify({
        'users': total_users,
        'balance': total_balance,
        'activeToday': total_users,
        'activeCodes': 0
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    """Получить всех пользователей"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    rows = cursor.fetchall()
    
    # Преобразуем в словари
    users = []
    for row in rows:
        users.append({
            'id': row[0],
            'telegram_id': row[1],
            'username': row[2],
            'first_name': row[3],
            'balance': row[4],
            'created_at': row[5]
        })
    
    conn.close()
    
    return jsonify({'users': users})

@app.route('/api/user/add', methods=['POST'])
def add_user():
    """Добавить пользователя"""
    data = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, balance)
            VALUES (?, ?, ?, ?)
        ''', (
            data.get('telegram_id'),
            data.get('username'),
            data.get('first_name'),
            data.get('balance', 0)
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/message/send', methods=['POST'])
def send_message():
    """Отправить сообщение через бота"""
    data = request.json
    
    try:
        BOT_TOKEN = '8402586959:AAGRTEGtSy7KoUlJDZvaNSxL3JKuZPWUMrY'
        
        import requests
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

# ===================== ЗАПУСК =====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
