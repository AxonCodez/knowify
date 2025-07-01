from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
import threading
import time

app = Flask(__name__)
app.secret_key = "knowify_secret_key"
socketio = SocketIO(app, cors_allowed_origins='*')

rooms = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create():
    room_id = request.form['room']
    admin_name = request.form['name']
    rooms[room_id] = {
        'admin': admin_name,
        'scores': {},
        'active_team': None,
        'question_type': None,
        'rounds': [],
        'quiz_started': False,
        'current_timer': 0,
        'current_round': '',
        'participants': {}
    }
    session['role'] = 'admin'
    session['name'] = admin_name
    session['room'] = room_id
    return redirect(url_for('room', room_id=room_id))

@app.route('/join', methods=['POST'])
def join():
    room_id = request.form['room']
    team = request.form['team']
    name = request.form['name']
    session['role'] = 'user'
    session['name'] = name
    session['team'] = team
    session['room'] = room_id
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>')
def room(room_id):
    role = session.get('role')
    name = session.get('name')
    team = session.get('team') if role == 'user' else None
    return render_template('room.html', room_id=room_id, role=role, name=name, team=team)

@socketio.on('join')
def handle_join(data):
    room = data['room']
    team = data['team']
    join_room(room)
    if team not in rooms[room]['scores']:
        rooms[room]['scores'][team] = 0
    emit('score_update', rooms[room]['scores'], room=room)
    emit('room_state', get_room_state(room), room=room)

@socketio.on('buzz')
def handle_buzz(data):
    emit('buzzed', data['team'], room=data['room'])

@socketio.on('reset_buzzer')
def reset_buzzer(data):
    emit('reset_buzzer', '', room=data['room'])

@socketio.on('award_points')
def award(data):
    room = data['room']
    team = data['team']
    points = int(data['points'])
    rooms[room]['scores'][team] += points
    emit('score_update', rooms[room]['scores'], room=room)

@socketio.on('start_quiz')
def start_quiz(data):
    room = data['room']
    rooms[room]['quiz_started'] = True
    emit('room_state', get_room_state(room), room=room)

@socketio.on('stop_quiz')
def stop_quiz(data):
    room = data['room']
    rooms[room]['quiz_started'] = False
    emit('room_state', get_room_state(room), room=room)

@socketio.on('add_round')
def add_round(data):
    room = data['room']
    rooms[room]['rounds'].append(f"Round {len(rooms[room]['rounds']) + 1}")
    emit('room_state', get_room_state(room), room=room)

@socketio.on('set_active_team')
def set_active_team(data):
    room = data['room']
    team = data['team']
    rooms[room]['active_team'] = team
    emit('room_state', get_room_state(room), room=room)

@socketio.on('set_question_type')
def set_question_type(data):
    room = data['room']
    qtype = data['qtype']
    rooms[room]['question_type'] = qtype
    emit('room_state', get_room_state(room), room=room)

@socketio.on('set_round_name')
def set_round_name(data):
    room = data['room']
    round_name = data['round_name']
    rooms[room]['current_round'] = round_name
    emit('room_state', get_room_state(room), room=room)

@socketio.on('start_timer')
def start_timer(data):
    room = data['room']
    seconds = int(data['seconds'])
    rooms[room]['current_timer'] = seconds

    def countdown():
        while rooms[room]['current_timer'] > 0:
            time.sleep(1)
            rooms[room]['current_timer'] -= 1
            socketio.emit('timer_update', rooms[room]['current_timer'], room=room)

    threading.Thread(target=countdown).start()

def get_room_state(room):
    return {
        'active_team': rooms[room]['active_team'],
        'question_type': rooms[room]['question_type'],
        'rounds': rooms[room]['rounds'],
        'quiz_started': rooms[room]['quiz_started'],
        'current_round': rooms[room]['current_round'],
        'timer': rooms[room]['current_timer']
    }

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000)
