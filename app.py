import os
from datetime import date

from flask import Flask, Response, render_template, request, redirect
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3307")),
    "user": os.environ.get("DB_USER", "fitness_user"),
    "password": os.environ.get("DB_PASSWORD", "1234"),
    "database": os.environ.get("DB_NAME", "fitness_tracker"),
}

CREATE_ACTIVITIES_SQL = """
CREATE TABLE IF NOT EXISTS Activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    date DATE NOT NULL,
    steps INT NOT NULL DEFAULT 0,
    calories_burned INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (user_id > 0),
    CHECK (steps >= 0),
    CHECK (calories_burned >= 0)
)
"""

SAMPLE_ACTIVITIES = [
    (1, "2026-04-13", 7400, 310),
    (1, "2026-04-14", 9200, 390),
    (1, "2026-04-15", 6800, 270),
    (2, "2026-04-13", 5100, 220),
    (2, "2026-04-14", 11200, 470),
    (2, "2026-04-16", 9700, 410),
    (3, "2026-04-15", 4300, 180),
    (3, "2026-04-16", 8000, 330),
    (3, "2026-04-17", 12300, 520),
]


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def ensure_schema():
    with get_db() as db:
        with db.cursor() as cursor:
            cursor.execute(CREATE_ACTIVITIES_SQL)
        db.commit()


def parse_int(value, label, errors, minimum=0):
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a whole number.")
        return None

    if number < minimum:
        errors.append(f"{label} must be at least {minimum}.")
        return None

    return number


def parse_date(value, errors):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append("Date must be a valid date.")
        return None

# Home Page
@app.route('/')
def index():
    try:
        stats = get_summary_stats()
        daily_totals = get_daily_totals(limit=5)
    except Error as exc:
        return render_template('index.html', stats=None, daily_totals=[], db_error=exc), 503

    return render_template('index.html', stats=stats, daily_totals=daily_totals, db_error=None)


@app.route('/service-worker.js')
def service_worker():
    return Response("", mimetype="application/javascript", headers={"Cache-Control": "no-store"})

# Add Activity
@app.route('/add_activity', methods=['GET', 'POST'])
def add_activity():
    if request.method == 'POST':
        errors = []
        user_id = parse_int(request.form.get('user_id'), "User ID", errors, minimum=1)
        activity_date = parse_date(request.form.get('date'), errors)
        steps = parse_int(request.form.get('steps'), "Steps", errors, minimum=0)
        calories = parse_int(request.form.get('calories'), "Calories", errors, minimum=0)

        if errors:
            return render_template('add_activity.html', errors=errors, form=request.form), 400

        query = "INSERT INTO Activities(user_id, date, steps, calories_burned) VALUES (%s,%s,%s,%s)"
        values = (user_id, activity_date, steps, calories)

        try:
            ensure_schema()
            with get_db() as db:
                with db.cursor() as cursor:
                    cursor.execute(query, values)
                db.commit()
        except Error as exc:
            errors.append(f"Could not save activity: {exc}")
            return render_template('add_activity.html', errors=errors, form=request.form), 503

        return redirect('/dashboard')

    return render_template('add_activity.html', errors=[], form={})


@app.route('/seed_sample_data', methods=['POST'])
def seed_sample_data():
    try:
        ensure_schema()
        with get_db() as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM Activities")
                activity_count = cursor.fetchone()[0]
                if activity_count == 0:
                    cursor.executemany("""
                        INSERT INTO Activities(user_id, date, steps, calories_burned)
                        VALUES (%s, %s, %s, %s)
                    """, SAMPLE_ACTIVITIES)
            db.commit()
    except Error as exc:
        return render_template('dashboard.html', db_error=exc, stats=None, daily_totals=[], user_totals=[], weekly_totals=[], recent=[]), 503

    return redirect('/dashboard')


def get_summary_stats():
    ensure_schema()
    with get_db() as db:
        with db.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) AS activity_count,
                    COUNT(DISTINCT user_id) AS user_count,
                    COALESCE(SUM(steps), 0) AS total_steps,
                    COALESCE(SUM(calories_burned), 0) AS total_calories,
                    COALESCE(ROUND(AVG(steps)), 0) AS avg_steps,
                    COALESCE(MAX(steps), 0) AS best_steps
                FROM Activities
            """)
            return cursor.fetchone()


def get_daily_totals(limit=None):
    query = """
        SELECT
            date,
            COUNT(*) AS entries,
            SUM(steps) AS total_steps,
            SUM(calories_burned) AS total_calories,
            ROUND(AVG(steps)) AS avg_steps
        FROM Activities
        GROUP BY date
        ORDER BY date DESC
    """
    if limit:
        query += " LIMIT %s"

    with get_db() as db:
        with db.cursor(dictionary=True) as cursor:
            cursor.execute(query, (limit,) if limit else None)
            return cursor.fetchall()


def get_user_totals():
    with get_db() as db:
        with db.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT
                    user_id,
                    COUNT(*) AS entries,
                    SUM(steps) AS total_steps,
                    SUM(calories_burned) AS total_calories,
                    ROUND(AVG(steps)) AS avg_steps,
                    MAX(steps) AS best_steps
                FROM Activities
                GROUP BY user_id
                HAVING SUM(steps) > 0
                ORDER BY total_steps DESC
            """)
            return cursor.fetchall()


def get_weekly_totals():
    with get_db() as db:
        with db.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT
                    YEARWEEK(date, 1) AS week_number,
                    MIN(date) AS week_start,
                    MAX(date) AS week_end,
                    COUNT(*) AS entries,
                    SUM(steps) AS total_steps,
                    SUM(calories_burned) AS total_calories
                FROM Activities
                GROUP BY YEARWEEK(date, 1)
                ORDER BY week_number DESC
            """)
            return cursor.fetchall()


def get_recent_activities():
    with get_db() as db:
        with db.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT user_id, date, steps, calories_burned
                FROM Activities
                ORDER BY date DESC, id DESC
                LIMIT 10
            """)
            return cursor.fetchall()


# Dashboard
@app.route('/dashboard')
def dashboard():
    try:
        stats = get_summary_stats()
        daily_totals = get_daily_totals()
        user_totals = get_user_totals()
        weekly_totals = get_weekly_totals()
        recent = get_recent_activities()
    except Error as exc:
        return render_template('dashboard.html', db_error=exc, stats=None, daily_totals=[], user_totals=[], weekly_totals=[], recent=[]), 503

    return render_template(
        'dashboard.html',
        db_error=None,
        stats=stats,
        daily_totals=daily_totals,
        user_totals=user_totals,
        weekly_totals=weekly_totals,
        recent=recent,
    )


if __name__ == '__main__':
    app.run(debug=True)
