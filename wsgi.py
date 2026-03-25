# This is the entry point for Gunicorn.
# Gunicorn will look for a variable named 'app' in this file.
from app import create_app, socketio
from app.config import Config

# Create the Flask application instance by calling the factory function
# and passing the configuration object directly.
app = create_app(Config)

# This allows running the file directly with python for development
if __name__ == '__main__':
    print("="*50)
    print("Starting Bug Tracker Development Server...")
    print("Access the application at: http://127.0.0.1:5000")
    print("="*50)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
