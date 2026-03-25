from app import create_app, db
from app.models import Role, Priority, Status

# Create a Flask app context
app = create_app()

with app.app_context():
    
    # --- 1. Seed Roles ---
    roles_to_add = [
        {'name': 'Admin', 'hierarchy_level': 1},
        {'name': 'Project Head', 'hierarchy_level': 2},
        {'name': 'Developer', 'hierarchy_level': 3},
        {'name': 'Testing Head', 'hierarchy_level': 2},
        {'name': 'Tester', 'hierarchy_level': 3},
    ]

    print("--- Seeding Roles ---")
    for role_data in roles_to_add:
        existing_role = Role.query.filter_by(name=role_data['name']).first()
        if not existing_role:
            new_role = Role(name=role_data['name'], hierarchy_level=role_data['hierarchy_level'])
            db.session.add(new_role)
            print(f"Added role: {role_data['name']}")
        else:
            print(f"Role '{role_data['name']}' already exists. Skipping.")


    # --- 2. Seed Priorities ---
    priorities_to_add = [
        {'name': 'Critical'},
        {'name': 'High'},
        {'name': 'Medium'},
        {'name': 'Low'},
    ]

    print("\n--- Seeding Priorities ---")
    for p_data in priorities_to_add:
        existing_priority = Priority.query.filter_by(name=p_data['name']).first()
        if not existing_priority:
            new_priority = Priority(name=p_data['name'])
            db.session.add(new_priority)
            print(f"Added priority: {p_data['name']}")
        else:
            print(f"Priority '{p_data['name']}' already exists. Skipping.")


    # --- 3. Seed Statuses ---
    # Role types: 'ALL', 'DEVELOPER' (Dev/Head), 'TESTER' (Tester/Head)
    statuses_to_add = [
        {'name': 'New', 'role_type': 'TESTER'},
        {'name': 'Assigned', 'role_type': 'DEVELOPER'},
        {'name': 'In Progress', 'role_type': 'DEVELOPER'},
        {'name': 'Resolved', 'role_type': 'DEVELOPER'},
        {'name': 'Reopened', 'role_type': 'TESTER'},
        {'name': 'Verified & Closed', 'role_type': 'TESTER'},
        {'name': 'Rejected', 'role_type': 'DEVELOPER'},
    ]

    print("\n--- Seeding Statuses ---")
    for s_data in statuses_to_add:
        existing_status = Status.query.filter_by(name=s_data['name']).first()
        if not existing_status:
            new_status = Status(name=s_data['name'], role_type=s_data['role_type'])
            db.session.add(new_status)
            print(f"Added status: {s_data['name']} (Type: {s_data['role_type']})")
        else:
            print(f"Status '{s_data['name']}' already exists. Skipping.")

    
    db.session.commit()
    print("\nDatabase initial lookup data seeding complete!")
