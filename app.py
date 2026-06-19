# Requirements:
# pip install flask flask-login flask-sqlalchemy flask-limiter werkzeug openai python-dotenv

import os
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# App setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["50 per day", "10 per minute"]
)

# OpenAI setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# DATABASE MODELS
# =========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, default=0)
    date = db.Column(db.DateTime, default=datetime.utcnow)

# =========================
# LOGIN MANAGER
# =========================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =========================
# REGISTER
# =========================

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json

        if not data.get('username') or not data.get('password'):
            return jsonify({"error": "Username and password required"}), 400

        existing_user = User.query.filter_by(
            username=data['username']
        ).first()

        if existing_user:
            return jsonify({"error": "Username already exists"}), 409

        hashed_pw = generate_password_hash(data['password'])

        new_user = User(
            username=data['username'],
            password_hash=hashed_pw
        )

        db.session.add(new_user)
        db.session.commit()

        return jsonify({"message": "Registration successful"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# LOGIN
# =========================

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    try:
        data = request.json

        user = User.query.filter_by(
            username=data['username']
        ).first()

        if user and check_password_hash(
            user.password_hash,
            data['password']
        ):
            login_user(user)

            session['chat_history'] = []

            return jsonify({
                "message": "Login successful"
            }), 200

        return jsonify({
            "error": "Invalid credentials"
        }), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
# LOGOUT
# =========================

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()

    return jsonify({
        "message": "Logged out successfully"
    })

# =========================
# AI CHAT
# =========================

@app.route('/chat', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def chat():
    try:
        user_message = request.json.get('message')

        if not user_message:
            return jsonify({
                "error": "Message required"
            }), 400

        if 'chat_history' not in session:
            session['chat_history'] = []

        session['chat_history'].append({
            "role": "user",
            "content": user_message
        })

        messages = [
            {
                "role": "system",
                "content": """
                You are an intelligent learning assistant.
                Help users improve in coding, AI, productivity, and business.
                Track weaknesses and guide improvement.
                """
            }
        ] + session['chat_history']

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        ai_reply = response.choices[0].message.content

        session['chat_history'].append({
            "role": "assistant",
            "content": ai_reply
        })

        session.modified = True

        return jsonify({
            "reply": ai_reply
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

# =========================
# SAVE USER PROGRESS
# =========================

@app.route('/progress', methods=['POST'])
@login_required
def save_progress():
    try:
        data = request.json

        progress = Progress(
            user_id=current_user.id,
            topic=data['topic'],
            score=data['score']
        )

        db.session.add(progress)
        db.session.commit()

        return jsonify({
            "message": "Progress saved"
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

# =========================
# VIEW PROGRESS
# =========================

@app.route('/my-progress', methods=['GET'])
@login_required
def my_progress():
    progress = Progress.query.filter_by(
        user_id=current_user.id
    ).all()

    result = []

    for p in progress:
        result.append({
            "topic": p.topic,
            "score": p.score,
            "date": p.date
        })

    return jsonify(result)

# =========================
# RUN APP
# =========================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True)
