# Run this script from the project root (bug_tracker1/) to fix the admin user's password hash.
#
# Usage: python admin_reset_password.py

import sys
import os

# Add the project directory to the path to ensure imports work correctly
# This ensures imports like 'from app import create_app' work.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the necessary Flask app context and models
from app import create_app, db, bcrypt
from app.models import User, Role # Ensure these models are correctly imported

# --- Configuration ---
ADMIN_USERNAME = 'admin'  # <--- Verify this is the username you are trying to log in with
NEW_PASSWORD = 'password' # IMPORTANT: Change this to the actual password you want to use
# ---------------------

def fix_admin_password():
    """
    Connects to the database, finds the admin user, and resets their password
    using the correct Flask-Bcrypt hashing function.
    """
    print(f"Starting application context...")
    app = create_app()

    with app.app_context():
        # 1. Find the user
        user = db.session.scalar(
            db.select(User).filter_by(username=ADMIN_USERNAME)
        )

        if not user:
            print(f"ERROR: User '{ADMIN_USERNAME}' not found in the database. Exiting.")
            return

        print(f"Found admin user: {user.username} (ID: {user.id})")
        print(f"Old hash (likely invalid): {user.password_hash[:20]}...")

        # 2. Generate and set the new, valid password hash
        try:
            # Hash the new password using the app's configured bcrypt instance
            # .decode('utf-8') is necessary because generate_password_hash returns bytes
            new_hash = bcrypt.generate_password_hash(NEW_PASSWORD).decode('utf-8')
            
            # Update the user record
            user.password_hash = new_hash
            db.session.commit()
            
            print("-------------------------------------------------------")
            print(f"SUCCESS: Password for user '{ADMIN_USERNAME}' updated.")
            print(f"New hash stored: {new_hash[:20]}...")
            print(f"The new password is: '{NEW_PASSWORD}'")
            print("-------------------------------------------------------")

        except Exception as e:
            db.session.rollback()
            print(f"An error occurred during password update: {e}")


if __name__ == '__main__':
    fix_admin_password()
