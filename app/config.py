import os

# Define the base directory of the project for use in file paths.
# Since this file is in the 'app' directory, basedir is the 'app' directory itself.
basedir = os.path.abspath(os.path.dirname(__file__))

# Get the project root directory (one level up from app)
project_root = os.path.dirname(basedir)

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-that-should-be-changed'

    # FIX APPLIED: Database will now be created in the project root, not inside the app folder
    # The final path will now be: '/path/to/bug_tracker1 6.1/app.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(project_root, 'app.db')
    
    # This setting is to silence a warning from Flask-SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload folder for screenshots (using project root)
    UPLOAD_FOLDER = os.path.join(project_root, 'static', 'screenshots')
    
    # Maximum content length for file uploads (16MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024