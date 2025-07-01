from flask import Flask, render_template, request, redirect, session, url_for
from flask_socketio import SocketIO, emit, join_room
import random
import string
import eventlet

eventlet.monkey_patch()

app = Flask(__name__)
app.secret_key = 'supersecret'
socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        room = request.form['room'].strip().upper()

        if role == 'admin':
            room = generate_code()
            rooms[room] = {
                'quiz_started': False,
                'question_type': '',
                'scores': {},
                'rounds': [],
                'current_round': '',
                'active_team': '',
                'current_timer': 0,
                'buzzer_enabled': False,
                'buzzed_order': [],
                'question_timer': 0,
                'question_timer_running': False
            }
            session['role'] = 'admin'
            session['name'] = name
            session['room'] = room
            return redirect(url_for('room_view'))
        else:
            team = request.form['team']
            if room not in rooms:
                return "Room does not exist."
            session['role'] = 'user'
            session['name'] = name
            session['room'] = room
            session['team'] = team
            return redirect(url_for('room_view'))

    return render_template('index.html')

@app.route('/room')
def room_view():
    if 'role' not in session:
        return redirect('/')
    return render_template('room.html',
                           room_id=session['room'],
                           name=session['name'],
                           role=session['role'],
                           team=session.get('team', ''))

# ========== SOCKET EVENTS ==========

@socketio.on('join')
def handle_join(data):
    room = data['room']
    team = data.get('team')
    join_room(room)

    if team:
        if team not in rooms[room]['scores']:
            rooms[room]['scores'][team] = 0

    emit('score_update', rooms[room]['scores'], room=room)
    emit('room_state', get_room_state(room), room=room)
    emit('buzzer_state', {
        'enabled': rooms[room]['buzzer_enabled'],
        'order': rooms[room]['buzzed_order']
    }, room=request.sid)
    emit('question_timer_update', {
        'seconds': rooms[room]['question_timer'],
        'running': rooms[room]['question_timer_running']
    }, room=request.sid)

@socketio.on('buzz')
def handle_buzz(data):
    room = data['room']
    team = data['team']
    if rooms[room]['buzzer_enabled'] and team not in rooms[room]['buzzed_order']:
        rooms[room]['buzzed_order'].append(team)
        emit('buzzer_state', {
            'enabled': True,
            'order': rooms[room]['buzzed_order']
        }, room=room)

@socketio.on('reset_buzzer')
def reset_buzzer(data):
    room = data['room']
    rooms[room]['buzzed_order'] = []
    emit('buzzer_state', {
        'enabled': rooms[room]['buzzer_enabled'],
        'order': []
    }, room=room)

@socketio.on('start_buzzer_timer')
def start_buzzer(data):
    room = data['room']
    rooms[room]['buzzer_enabled'] = True
    rooms[room]['buzzed_order'] = []
    emit('buzzer_state', {
        'enabled': True,
        'order': []
    }, room=room)

@socketio.on('stop_buzzer_timer')
def stop_buzzer(data):
    room = data['room']
    rooms[room]['buzzer_enabled'] = False
    emit('buzzer_state', {
        'enabled': False,
        'order': rooms[room]['buzzed_order']
    }, room=room)

@socketio.on('award_points')
def handle_award(data):
    room = data['room']
    team = data['team']
    points = int(data['points'])
    if team in rooms[room]['scores']:
        rooms[room]['scores'][team] += points
    emit('score_update', rooms[room]['scores'], room=room)

@socketio.on('set_active_team')
def handle_set_active(data):
    rooms[data['room']]['active_team'] = data['team']
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('set_question_type')
def handle_qtype(data):
    rooms[data['room']]['question_type'] = data['qtype']
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('add_round')
def handle_add_round(data):
    rooms[data['room']]['rounds'].append(f"Round {len(rooms[data['room']]['rounds'])+1}")
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('set_round_name')
def handle_set_round(data):
    rooms[data['room']]['current_round'] = data['round_name']
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('start_quiz')
def handle_start(data):
    rooms[data['room']]['quiz_started'] = True
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('stop_quiz')
def handle_stop(data):
    rooms[data['room']]['quiz_started'] = False
    emit('room_state', get_room_state(data['room']), room=data['room'])

@socketio.on('start_timer')
def handle_timer(data):
    room = data['room']
    seconds = int(data['seconds'])
    rooms[room]['current_timer'] = seconds
    emit('timer_update', seconds, room=room)

    def countdown():
        nonlocal seconds
        while seconds > 0:
            eventlet.sleep(1)
            seconds -= 1
            rooms[room]['current_timer'] = seconds
            emit('timer_update', seconds, room=room)

    socketio.start_background_task(countdown)

@socketio.on('start_question_timer')
def start_question_timer(data):
    room = data['room']
    seconds = int(data['seconds'])
    rooms[room]['question_timer'] = seconds
    rooms[room]['question_timer_running'] = True
    emit('question_timer_update', {'seconds': seconds, 'running': True}, room=room)

    def countdown():
        nonlocal seconds
        while seconds > 0 and rooms[room]['question_timer_running']:
            eventlet.sleep(1)
            seconds -= 1
            rooms[room]['question_timer'] = seconds
            emit('question_timer_update', {'seconds': seconds, 'running': True}, room=room)
        rooms[room]['question_timer_running'] = False
        emit('question_timer_update', {'seconds': seconds, 'running': False}, room=room)

    socketio.start_background_task(countdown)

@socketio.on('stop_question_timer')
def stop_question_timer(data):
    room = data['room']
    rooms[room]['question_timer_running'] = False
    emit('question_timer_update', {
        'seconds': rooms[room]['question_timer'],
        'running': False
    }, room=room)

@socketio.on('reset_question')
def reset_question(data):
    room = data['room']
    rooms[room]['question_type'] = ''
    rooms[room]['active_team'] = ''
    rooms[room]['question_timer'] = 0
    rooms[room]['question_timer_running'] = False
    emit('room_state', get_room_state(room), room=room)
    emit('question_timer_update', {
        'seconds': 0,
        'running': False
    }, room=room)

def get_room_state(room):
    return {
        'active_team': rooms[room]['active_team'],
        'question_type': rooms[room]['question_type'],
        'rounds': rooms[room]['rounds'],
        'quiz_started': rooms[room]['quiz_started'],
        'current_round': rooms[room]['current_round'],
        'timer': rooms[room]['current_timer'],
        'question_timer': rooms[room]['question_timer'],
        'question_timer_running': rooms[room]['question_timer_running']
    }

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000)
