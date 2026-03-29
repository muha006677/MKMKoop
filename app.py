from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'instance' / 'mkmkoop.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-in-production')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            task_date TEXT NOT NULL,
            due_time TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def login_required():
    return current_user() is not None


def add_history(user_id: int, action: str, detail: str):
    conn = get_db()
    conn.execute(
        'INSERT INTO history (user_id, action, detail, created_at) VALUES (?, ?, ?, ?)',
        (user_id, action, detail, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def parse_due_datetime(task_row):
    return datetime.fromisoformat(f"{task_row['task_date']}T{task_row['due_time']}:00")


@app.context_processor
def inject_globals():
    user = current_user()
    pending_count = 0
    if user:
        conn = get_db()
        pending_count = conn.execute(
            'SELECT COUNT(*) AS c FROM tasks WHERE user_id = ? AND completed = 0',
            (user['id'],)
        ).fetchone()['c']
        conn.close()
    return {'current_user': user, 'pending_count': pending_count, 'now': datetime.utcnow()}


@app.route('/')
def home():
    user = current_user()
    tasks = []
    stats = {'pending': 0, 'done': 0, 'avg': 0}
    if user:
        conn = get_db()
        tasks = conn.execute(
            'SELECT * FROM tasks WHERE user_id = ? AND completed = 0 ORDER BY task_date ASC, due_time ASC',
            (user['id'],)
        ).fetchall()
        done = conn.execute('SELECT COUNT(*) AS c FROM tasks WHERE user_id = ? AND completed = 1', (user['id'],)).fetchone()['c']
        pending = len(tasks)
        avg = round(sum(int(t['progress']) for t in tasks) / pending) if pending else 0
        stats = {'pending': pending, 'done': done, 'avg': avg}
        conn.close()
    return render_template('home.html', tasks=tasks, stats=stats)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('请填写用户名和密码', 'error')
            return redirect(url_for('register'))

        conn = get_db()
        exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if exists:
            conn.close()
            flash('用户名已存在', 'error')
            return redirect(url_for('register'))

        cur = conn.execute(
            'INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), datetime.utcnow().isoformat())
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()

        session['user_id'] = user_id
        add_history(user_id, '注册成功', f'账户 {username} 已创建')
        flash('注册成功', 'success')
        return redirect(url_for('home'))
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if not user or not check_password_hash(user['password_hash'], password):
            flash('用户名或密码错误', 'error')
            return redirect(url_for('login'))
        session['user_id'] = user['id']
        flash('登录成功', 'success')
        return redirect(url_for('home'))
    return render_template('auth.html', mode='login')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('home'))


@app.route('/tasks')
def tasks_page():
    if not login_required():
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    user = current_user()
    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'all')
    conn = get_db()
    query = 'SELECT * FROM tasks WHERE user_id = ?'
    params = [user['id']]
    if q:
        query += ' AND (title LIKE ? OR content LIKE ?)'
        params.extend([f'%{q}%', f'%{q}%'])
    if status == 'completed':
        query += ' AND completed = 1'
    elif status == 'pending':
        query += ' AND completed = 0'
    query += ' ORDER BY completed ASC, task_date ASC, due_time ASC, id DESC'
    tasks = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return render_template('tasks.html', tasks=tasks, q=q, status=status)


@app.route('/tasks/create', methods=['POST'])
def create_task():
    if not login_required():
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    task_date = request.form.get('task_date', '').strip()
    due_time = request.form.get('due_time', '').strip()
    progress = max(0, min(100, int(request.form.get('progress', 0) or 0)))

    if not all([title, content, task_date, due_time]):
        flash('请完整填写任务信息', 'error')
        return redirect(url_for('tasks_page'))

    completed = 1 if progress >= 100 else 0
    now = datetime.utcnow().isoformat()
    user = current_user()
    conn = get_db()
    conn.execute(
        '''INSERT INTO tasks (user_id, title, content, task_date, due_time, progress, completed, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user['id'], title, content, task_date, due_time, progress, completed, now, now)
    )
    conn.commit()
    conn.close()
    add_history(user['id'], '创建任务', f'已创建任务《{title}》')
    if completed:
        add_history(user['id'], '任务完成', f'《{title}》已完成')
    flash('任务已创建', 'success')
    return redirect(url_for('tasks_page'))


@app.route('/tasks/<int:task_id>/update', methods=['POST'])
def update_task(task_id):
    if not login_required():
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    progress = max(0, min(100, int(request.form.get('progress', 0) or 0)))
    user = current_user()
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (task_id, user['id'])).fetchone()
    if not task:
        conn.close()
        flash('任务不存在', 'error')
        return redirect(url_for('tasks_page'))
    completed = 1 if progress >= 100 else 0
    conn.execute(
        'UPDATE tasks SET progress = ?, completed = ?, updated_at = ? WHERE id = ? AND user_id = ?',
        (progress, completed, datetime.utcnow().isoformat(), task_id, user['id'])
    )
    conn.commit()
    conn.close()
    add_history(user['id'], '更新进度', f'《{task["title"]}》进度更新为 {progress}%')
    if progress >= 100 and int(task['progress']) < 100:
        add_history(user['id'], '任务完成', f'《{task["title"]}》已完成')
    flash('任务进度已更新', 'success')
    return redirect(url_for('tasks_page'))


@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    if not login_required():
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    user = current_user()
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (task_id, user['id'])).fetchone()
    if task:
        conn.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user['id']))
        conn.commit()
        add_history(user['id'], '删除任务', f'已删除任务《{task["title"]}》')
        flash('任务已删除', 'success')
    conn.close()
    return redirect(url_for('tasks_page'))


@app.route('/history')
def history_page():
    if not login_required():
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    user = current_user()
    conn = get_db()
    items = conn.execute(
        'SELECT * FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 200',
        (user['id'],)
    ).fetchall()
    conn.close()
    return render_template('history.html', items=items)


@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok', 'service': 'MKMKoop', 'time': datetime.utcnow().isoformat()})


@app.template_filter('deadline_iso')
def deadline_iso(task):
    return f"{task['task_date']}T{task['due_time']}:00"


@app.template_filter('task_state')
def task_state(task):
    if int(task['completed']) == 1 or int(task['progress']) >= 100:
        return 'completed'
    try:
        if parse_due_datetime(task) < datetime.now():
            return 'overdue'
    except Exception:
        pass
    return 'pending'


@app.template_filter('task_state_label')
def task_state_label(task):
    state = task_state(task)
    return {'completed': '已完成', 'overdue': '已超时', 'pending': '进行中'}[state]


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    init_db()
