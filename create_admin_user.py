import os
from app import create_app, db, bcrypt
from app.models import User, Role

# Create a Flask application instance
app = create_app()

def create_admin_user():
    """
    Creates an initial admin user for the application.
    """
    with app.app_context():
        print("Creating initial admin user...")
        # Check if an admin role exists, if not, create it
        admin_role = Role.query.filter_by(name='Admin').first()
        if not admin_role:
            print("Admin role not found. Creating it now...")
            admin_role = Role(name='Admin')
            db.session.add(admin_role)
            db.session.commit()

        # Check if an admin user already exists to prevent duplicates
        existing_user = User.query.filter_by(username='admin').first()
        if existing_user:
            print("Admin user already exists. Skipping creation.")
        else:
            # Hash the default password before saving
            hashed_password = bcrypt.generate_password_hash('password').decode('utf-8')
            
            # Create a new user with the admin role, using the correct argument
            admin_user = User(
                username='admin',
                password_hash=hashed_password,
                name='Administrator',
                role=admin_role
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user 'admin' created with password 'password'.")
            print("Please log in with these credentials and change them immediately.")

if __name__ == '__main__':
    create_admin_user()
