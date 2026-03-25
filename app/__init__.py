import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_migrate import Migrate 
from flask_login import LoginManager # 1. Import LoginManager
from .config import Config

# ----------------------------------------------------------------------
# FIX 1: Correctly calculate the project root directory.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# ----------------------------------------------------------------------

db = SQLAlchemy()
migrate = Migrate() 
bcrypt = Bcrypt()
socketio = SocketIO(cors_allowed_origins="*")

# 2. Initialize LoginManager instance globally
login_manager = LoginManager()
# Set the view function name for the login page (e.g., used by @login_required)
login_manager.login_view = 'main.login'

def create_app(config_class=Config):
    """
    Application factory function.
    Creates and configures the Flask application.
    """
    
    # CRITICAL FIX 2: Explicitly set the static folder using the corrected project root path.
    app = Flask(__name__,
                static_url_path='/static',
                static_folder=os.path.join(project_root, 'static'))
    
    # Load configuration directly from the imported Config class.
    app.config.from_object(config_class)
    
    db.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)
    
    # CRITICAL STEP: Initialize Flask-Migrate with the app and db objects
    migrate.init_app(app, db)

    # 3. Initialize Flask-Login with the app object
    login_manager.init_app(app)

    with app.app_context():
        # IMPORTANT: Import User model here to avoid circular dependencies
        from app.models import User
        
        # Define the user_loader callback
        @login_manager.user_loader
        def load_user(user_id):
            """Given a user ID, return the corresponding User object."""
            # Ensure the ID is cast to int before querying
            return User.query.get(int(user_id))

        # Import and register blueprints
        from app.routes import main as main_blueprint
        
        # FIX: Remove url_prefix='/admin'. The 'main' blueprint should register 
        # its routes directly under the root path (/).
        app.register_blueprint(main_blueprint) 
        
        # *** DEBUG STEP ***
        print(f"Flask FINAL static folder path: {app.static_folder}")
        
    return app
