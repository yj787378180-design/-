
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import sqlite3
from datetime import datetime
from collections import Counter

app = Flask(__name__)
CORS(app)
DB_FILE = 'whatsapp_full.db'

# ------------------ 数据库初始化 ------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT 1
        )
    ''')
    # 号码表
    c.execute('''
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            sub_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_duplicate BOOLEAN DEFAULT 0,
            duplicate_sub_id INTEGER,
            FOREIGN KEY(sub_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

# 默认 Admin 用户
def init_admin():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        hashed = generate_password_hash("admin123")
        c.execute("INSERT INTO users (username,password,role) VALUES (?, ?, ?)",
                  ("admin", hashed, "admin"))
        conn.commit()
    conn.close()

# ------------------ 用户接口 ------------------
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data['username']
    password = data['password']
    role = data['role']
    hashed = generate_password_hash(password)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                  (username, hashed, role))
        conn.commit()
        return jsonify({'status': 'success', 'message': f'{role}账号创建成功'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '用户名已存在'})
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, password, role, active FROM users WHERE username=?', (username,))
    user = c.fetchone()
    conn.close()
    if not user:
        return jsonify({'status': 'error', 'message': '用户名不存在'})
    if not user[3]:
        return jsonify({'status': 'error', 'message': '账号被禁用'})
    if check_password_hash(user[1], password):
        return jsonify({'status': 'success', 'user_id': user[0], 'role': user[2]})
    return jsonify({'status': 'error', 'message': '密码错误'})

# ------------------ 上传号码 ------------------
@app.route('/upload_number', methods=['POST'])
def upload_number():
    data = request.json
    phone = data['phone']
    sub_id = data['sub_id']
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, sub_id FROM numbers WHERE phone=?', (phone,))
    res = c.fetchone()
    if res:
        is_duplicate = 1
        duplicate_sub_id = res[1]
    else:
        is_duplicate = 0
        duplicate_sub_id = None
    c.execute('INSERT INTO numbers (phone, sub_id, is_duplicate, duplicate_sub_id) VALUES (?, ?, ?, ?)',
              (phone, sub_id, is_duplicate, duplicate_sub_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'is_duplicate': is_duplicate, 'duplicate_sub_id': duplicate_sub_id})

# ------------------ 用户上传明细 ------------------
@app.route('/user_numbers', methods=['GET'])
def user_numbers():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT users.username, numbers.phone, numbers.created_at
        FROM numbers
        JOIN users ON numbers.sub_id = users.id
        ORDER BY numbers.created_at DESC
    ''')
    rows = c.fetchall()
    conn.close()

    result = {}
    for username, phone, created_at in rows:
        if username not in result:
            result[username] = []
        result[username].append({'phone': phone, 'created_at': created_at})
    return jsonify(result)

# ------------------ 今日上传统计 ------------------
@app.route('/daily_stats', methods=['GET'])
def daily_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT users.username, COUNT(numbers.id)
        FROM numbers
        JOIN users ON numbers.sub_id = users.id
        WHERE DATE(numbers.created_at) = ?
        GROUP BY users.username
    ''', (today,))
    rows = c.fetchall()
    conn.close()

    total = sum([count for _, count in rows])
    result = {'total': total, 'users': {username: count for username, count in rows}}
    return jsonify(result)

# ------------------ 指定时间段对比 ------------------
@app.route('/compare_users', methods=['POST'])
def compare_users():
    data = request.json
    start = data.get('start')
    end = data.get('end')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = '''
        SELECT users.username, COUNT(numbers.id)
        FROM numbers
        JOIN users ON numbers.sub_id = users.id
        WHERE 1=1
    '''
    params = []
    if start:
        query += " AND created_at >= ?"
        params.append(start)
    if end:
        query += " AND created_at <= ?"
        params.append(end)
    query += " GROUP BY users.username"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    result = {username: count for username, count in rows}
    return jsonify(result)

# ------------------ 数据统计 ------------------
@app.route('/stats', methods=['POST'])
def stats():
    data = request.json
    start = data.get('start')
    end = data.get('end')
    sub_id = data.get('sub_id')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = 'SELECT phone, sub_id, created_at FROM numbers WHERE 1=1'
    params = []
    if start:
        query += ' AND created_at >= ?'
        params.append(start)
    if end:
        query += ' AND created_at <= ?'
        params.append(end)
    if sub_id:
        query += ' AND sub_id = ?'
        params.append(sub_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    total = len(rows)
    phones = [r[0] for r in rows]
    duplicates = sum([phones.count(p)-1 for p in set(phones)])
    duplicate_rate = duplicates / total if total else 0
    hourly_counter = Counter()
    for r in rows:
        hour = datetime.strptime(r[2], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H')
        hourly_counter[hour] += 1
    return jsonify({
        'total': total,
        'duplicates': duplicates,
        'duplicate_rate': round(duplicate_rate, 2),
        'hourly': hourly_counter
    })

# ------------------ 用户管理 ------------------
@app.route('/users', methods=['GET'])
def list_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, username, role, active, created_at FROM users')
    rows = c.fetchall()
    conn.close()
    users = []
    for r in rows:
        users.append({'id': r[0], 'username': r[1], 'role': r[2], 'active': bool(r[3]), 'created_at': r[4]})
    return jsonify(users)

@app.route('/users/<int:user_id>/toggle', methods=['POST'])
def toggle_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE users SET active = NOT active WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# ------------------ 静态前端 ------------------
@app.route('/')
def index():
    return app.send_static_file('index.html')

# ------------------ 启动 ------------------
if __name__ == '__main__':
    init_db()
    init_admin()
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
