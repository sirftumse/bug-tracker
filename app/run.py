from app import create_app, socketio
from app.config import Config

app = create_app(Config)

if __name__ == '__main__':
    print("="*50)
    print("Starting Bug Tracker Development Server...")
    print("Access the application at: http://127.0.0.1:5000")
    print("="*50)
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)