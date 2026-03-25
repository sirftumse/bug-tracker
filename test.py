import eventlet
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# This is critical for eventlet to work with Flask-SocketIO
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key-that-should-be-more-secure'
socketio = SocketIO(app, async_mode='eventlet')

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>WebSocket Test</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                const socket = io();
                
                socket.on('connect', function() {
                    console.log('Connected!');
                    const status = document.getElementById('status');
                    status.textContent = 'Status: Connected';
                    status.style.color = 'green';
                });
                
                socket.on('disconnect', function() {
                    console.log('Disconnected!');
                    const status = document.getElementById('status');
                    status.textContent = 'Status: Disconnected';
                    status.style.color = 'red';
                });
            });
        </script>
    </head>
    <body>
        <h1>WebSocket Connection Test</h1>
        <p id="status">Status: Connecting...</p>
    </body>
    </html>
    """

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # Use this for local testing only
    socketio.run(app, debug=True)
