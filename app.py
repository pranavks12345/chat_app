from flask import Flask, render_template, request, jsonify, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store active users and chat history
active_users = {}
chat_history = []
typing_users = set()

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    username = request.form.get('username', 'Anonymous')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        try:
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            
            # Create file message
            file_message = {
                'id': str(uuid.uuid4()),
                'username': username,
                'type': 'file',
                'filename': filename,
                'file_url': url_for('static', filename=f'uploads/{unique_filename}'),
                'file_size': format_file_size(file_size),
                'timestamp': datetime.now().isoformat()
            }
            
            # Add to chat history
            chat_history.append(file_message)
            
            # Emit to all connected clients
            socketio.emit('new_message', file_message)
            
            return jsonify({'success': True, 'message': file_message})
            
        except Exception as e:
            return jsonify({'error': f'File upload failed: {str(e)}'}), 500
    
    return jsonify({'error': 'File type not allowed'}), 400

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.sid
    if user_id in active_users:
        username = active_users[user_id]
        del active_users[user_id]
        
        # Remove from typing users
        typing_users.discard(username)
        
        # Notify others about user leaving
        emit('user_left', {
            'username': username,
            'user_count': len(active_users)
        }, broadcast=True)
        
        # Update user list
        emit('users_update', list(active_users.values()), broadcast=True)
        
        print(f'Client disconnected: {user_id} ({username})')

@socketio.on('join_chat')
def handle_join(data):
    username = data['username']
    user_id = request.sid
    
    # Store user
    active_users[user_id] = username
    
    # Send chat history to new user
    emit('chat_history', chat_history)
    
    # Send current users list
    emit('users_update', list(active_users.values()))
    
    # Notify others about new user
    emit('user_joined', {
        'username': username,
        'user_count': len(active_users)
    }, broadcast=True, include_self=False)
    
    print(f'User joined: {username} ({user_id})')

@socketio.on('send_message')
def handle_message(data):
    user_id = request.sid
    if user_id not in active_users:
        return
    
    username = active_users[user_id]
    
    message = {
        'id': str(uuid.uuid4()),
        'username': username,
        'type': 'text',
        'text': data['message'],
        'timestamp': datetime.now().isoformat()
    }
    
    # Add to chat history
    chat_history.append(message)
    
    # Broadcast to all clients
    emit('new_message', message, broadcast=True)

@socketio.on('typing')
def handle_typing():
    user_id = request.sid
    if user_id in active_users:
        username = active_users[user_id]
        typing_users.add(username)
        emit('user_typing', {
            'username': username,
            'typing_users': list(typing_users)
        }, broadcast=True, include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing():
    user_id = request.sid
    if user_id in active_users:
        username = active_users[user_id]
        typing_users.discard(username)
        emit('user_stop_typing', {
            'username': username,
            'typing_users': list(typing_users)
        }, broadcast=True, include_self=False)

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'active_users': len(active_users),
        'total_messages': len(chat_history)
    })

if __name__ == '__main__':
    print("🚀 Starting Python Chat Server...")
    print("📱 Open your browser to: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)