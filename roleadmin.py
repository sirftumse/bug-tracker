import os
from app import create_app, db
# Ensure this import path for your Role model is correct:
from app.models import Role 

def create_default_roles():
    """Initializes the Flask app context and ensures default roles are present."""
    print("Initializing Flask application for role creation...")
    
    app = create_app()
    with app.app_context():
        
        # Define the essential roles for a bug tracker application.
        # Ensure the IDs match what you used for the admin user (role_id=1)
        DEFAULT_ROLES = [
            # ID 1 MUST correspond to the Admin role, as we set admin.role_id = 1
            {'id': 1, 'name': 'Admin', 'description': 'Full system administrative access'},
            {'id': 2, 'name': 'Developer', 'description': 'Can resolve and update bug reports'},
            {'id': 3, 'name': 'Reporter', 'description': 'Can submit new bug reports and track their own issues'}
        ]

        roles_added = 0
        
        for role_data in DEFAULT_ROLES:
            # Check if the role already exists by ID
            role_by_id = Role.query.get(role_data['id'])
            
            if role_by_id:
                print(f"Role ID {role_data['id']} ({role_by_id.name}) already exists. Skipping.")
                # We can also update the name/description if they changed, but for now, we skip.
                continue

            # Check if the role already exists by name (for safety)
            role_by_name = Role.query.filter_by(name=role_data['name']).first()
            if role_by_name:
                print(f"Role '{role_data['name']}' already exists with ID {role_by_name.id}. Skipping.")
                continue


            print(f"Adding new role: {role_data['name']} (ID: {role_data['id']})...")
            
            # Create a new Role instance, setting the ID manually for deterministic ordering
            new_role = Role(
                id=role_data['id'],
                name=role_data['name'],
                description=role_data['description']
            )
            
            db.session.add(new_role)
            roles_added += 1

        if roles_added > 0:
            try:
                db.session.commit()
                print("---------------------------------------")
                print(f"✅ SUCCESS! Added {roles_added} new roles to the database.")
                print("---------------------------------------")
            except Exception as e:
                db.session.rollback()
                print(f"❌ ERROR: Failed to commit roles to the database. Rolling back.")
                print(f"Traceback hint: {e}")
        else:
            print("No new roles needed to be added.")


if __name__ == '__main__':
    create_default_roles()
