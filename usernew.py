import os
from app import create_app, db, bcrypt # Import bcrypt for consistent password hashing
from app.models import User, Role # Import Role to look up the role_id

# --- Configuration for the New Admin User ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'      # !!! CHANGE THIS TO A SECURE PASSWORD AFTER LOGIN !!!
ADMIN_NAME = 'Administrator'
ADMIN_ROLE_NAME = 'Admin'        # Use the name to find the ID dynamically
# ---------------------------------------------

def create_admin_user():
    """Initializes the Flask app context and creates a new admin user."""
    print("Initializing Flask application...")
    
    app = create_app()
    with app.app_context():
        
        # 0. Find the Admin Role ID dynamically
        try:
            admin_role = Role.query.filter_by(name=ADMIN_ROLE_NAME).first()
            if not admin_role:
                print(f"🚨 CRITICAL ERROR: Role '{ADMIN_ROLE_NAME}' not found. Please run seed_initial_data.py first.")
                return
            ADMIN_ROLE_ID = admin_role.id
        except Exception as e:
            print(f"🚨 CRITICAL ERROR: Failed to find Admin Role. Ensure tables are created and seeded. Error: {e}")
            return
            
        
        # 1. Check if an admin user already exists
        try:
            user = User.query.filter_by(username=ADMIN_USERNAME).first()
        except Exception as e:
            print(f"🚨 CRITICAL ERROR: Could not query the User table. Have you run create_db.py? Error: {e}")
            return

        if user:
            print(f"User '{ADMIN_USERNAME}' already exists. Skipping creation.")
            return

        print(f"Creating new user: {ADMIN_USERNAME} with role ID {ADMIN_ROLE_ID}...")

        # 2. Create the new user instance using bcrypt for hashing
        # This ensures the password hash is compatible with your User model's check_password method
        hashed_password = bcrypt.generate_password_hash(ADMIN_PASSWORD).decode('utf-8') 

        try:
            new_user = User(
                username=ADMIN_USERNAME, 
                password_hash=hashed_password,
                name=ADMIN_NAME,
                role_id=ADMIN_ROLE_ID
            )
        except Exception as e:
            print(f"❌ ERROR: Failed to instantiate User object. Traceback hint: {e}")
            return


        # 3. Add to the database and commit
        db.session.add(new_user)
        db.session.commit()

        print("---------------------------------------")
        print("✅ SUCCESS! Admin Account Created.")
        print(f"Username: {ADMIN_USERNAME}")
        print(f"Password: {ADMIN_PASSWORD}")
        print("---------------------------------------")


if __name__ == '__main__':
    create_admin_user()
