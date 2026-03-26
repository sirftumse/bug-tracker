import os
import json
import io
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, g, abort
from app import db, bcrypt, socketio
from app.models import User, Role, Project, Bug, BugHistory, Module, SubModule, Priority, Status, Comment, BugScreenshot, Release, user_project_assignment
from functools import wraps
from datetime import datetime
from flask_login import current_user
from werkzeug.utils import secure_filename
from base64 import b64decode
from flask_socketio import emit
from sqlalchemy.orm import joinedload # Ensure this is imported at the top of your routes file
from app.models import User, Role, Project, Bug, BugHistory, Module, SubModule, Priority, Status, StatusTransition, Comment, BugScreenshot, Release, user_project_assignment
# Added StatusTransition to the imports
import traceback 

main = Blueprint('main', __name__)


# 1. Get the absolute path of the current file (routes.py)
current_file_path = os.path.abspath(__file__)
print("--- PATH DEBUG START ---")
print(f"1. Current File Path (__file__): {current_file_path}")

# 2. Go up one level (from routes.py to app)
app_dir = os.path.dirname(current_file_path)
print(f"2. App Directory (bug_tracker1/app): {app_dir}")

# 3. Go up two levels (from app to bug_tracker1 - THIS SHOULD BE THE PROJECT ROOT)
project_root = os.path.dirname(app_dir)
print(f"3. Project Root (bug_tracker1): {project_root}")

# 4. Define the final upload folder path
UPLOAD_FOLDER = os.path.join(project_root, 'static', 'screenshots')

# Final path establishment
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print("="*80)
    print(f"*** FINAL RELIABLE ABSOLUTE PATH (SAVE LOCATION): {UPLOAD_FOLDER} ***")
    print("="*80)
    print("--- PATH DEBUG END ---")
except Exception as e:
    # Print the error if directory creation fails (e.g., PermissionError)
    print(f"!!! CRITICAL ERROR: Failed to create upload folder at {UPLOAD_FOLDER}. Error: {e}")
    print("--- PATH DEBUG END ---")

# --------------------------------------------------------------------------------

@main.before_request
def load_current_user():
    """Loads the current user from the session and assigns it to Flask's global context (g)."""
    user_id = session.get('user_id')
    g.user = User.query.get(user_id) if user_id else None

# Custom decorator to check if user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# A more robust decorator to check for multiple roles
def permission_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = User.query.get(session.get('user_id'))
            if user and user.role.name in allowed_roles:
                return f(*args, **kwargs)
            else:
                flash("You do not have permission to view this page.", 'danger')
                return redirect(url_for('main.dashboard'))
        return decorated_function
    return decorator

def _get_role_type_for_user(user):
    """Helper function to map user role names to the Status role_type for filtering."""
    if user.role.name in ['Developer', 'Project Head']:
        return 'DEVELOPER'
    elif user.role.name in ['Tester', 'Testing Head']:
        return 'TESTER'
    return 'ALL' # Default for Admin/others who can manage all states

@main.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash(f'Login successful! Welcome, {user.name}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@main.route('/logout', methods=['GET', 'POST'])  # Updated to accept POST
def logout():
    """Handles user logout."""
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))


@main.route('/')
def index():
    """Redirect to dashboard if logged in, else login page."""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))


@main.route('/dashboard')
@login_required
def dashboard():
    """Displays the main dashboard with assigned and reported bugs/projects, adapted for Developer/Tester roles."""
    user = g.user
    
    # CRITICAL NEW CHECK: Ensure the user object itself exists before proceeding.
    # The crash happens here if g.user is None, as None has no attribute 'role'.
    if user is None:
        # This should ideally be handled by @login_required, but this is a final defensive step.
        print("WARNING: User object (g.user) was None in dashboard route.")
        return render_template('dashboard.html', 
                               user=None, 
                               projects=[],
                               assigned_bugs=[],
                               reported_bugs=[])


    # Safety Check 2 (Original Fix): If the user exists, but doesn't have an assigned role (user.role is None)
    if not user.role:
        # Fallback for users without an assigned role. They see nothing assigned/reported.
        return render_template('dashboard.html', 
                               user=user, 
                               projects=[],
                               assigned_bugs=[],
                               reported_bugs=[])

    # 1. Determine which projects the user can see
    # We now safely check user.role is not None before accessing user.role.name
    if user.role.name in ['Admin', 'Testing Head', 'Project Head']:
        # Admins and Heads see all projects
        projects = Project.query.all()
    elif user.role.name in ['Developer', 'Tester']:
        # Devs and Testers see projects they are assigned to
        projects = user.projects
    else:
        projects = []

    # 2. Determine "Assigned Bugs" based on role
    assigned_bugs = []
    
    if user.role.name in ['Tester', 'Testing Head']:
        # Logic for Testers: Bugs related to releases they are assigned to test
        assigned_releases = user.assigned_releases
        if assigned_releases:
            release_ids = [r.id for r in assigned_releases]
            assigned_bugs = Bug.query.filter(Bug.release_id.in_(release_ids)).order_by(Bug.timestamp.desc()).all()
            
    elif user.role.name in ['Developer', 'Project Head', 'Admin']:
        # Logic for Devs/PHs/Admins: Bugs directly assigned to them
        assigned_bugs = Bug.query.filter_by(assigned_to_id=user.id).order_by(Bug.timestamp.desc()).all()
    
    # 3. Fetch bugs reported by the current user (works for all roles)
    reported_bugs = Bug.query.filter_by(reporter_id=user.id).order_by(Bug.timestamp.desc()).all()
    
    # Pass the user object as 'user' to match the template
    return render_template('dashboard.html', 
                           user=user, 
                           projects=projects,
                           assigned_bugs=assigned_bugs,
                           reported_bugs=reported_bugs)


@main.route('/create_user', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def create_user():
    """Admin route to create a new user."""
    user = g.user
    roles = Role.query.all()
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        role_id = request.form.get('role')
        
        # Add basic validation
        if not all([username, name, password, role_id]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('main.create_user'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('main.create_user'))

        # Validate that the role_id is valid
        role = Role.query.get(role_id)
        if not role:
            flash('Invalid role selected. Please choose a valid role.', 'danger')
            return redirect(url_for('main.create_user'))

        try:
            # Create user and set password
            new_user = User(username=username, name=name, role_id=role_id)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f'User "{name}" created successfully!', 'success')
            return redirect(url_for('main.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('main.create_user'))
            
    return render_template('create_user.html', roles=roles, user=user)
@main.route('/admin/manage_users', methods=['GET'])
@login_required
@permission_required(allowed_roles=['Admin'])
def manage_users():
    """Admin route to display the list of all users."""
    user = g.user
    
    # Fetch all users, excluding the current Admin user from the list if desired
    users = User.query.order_by(User.id).all()
    
    # Fetch all roles for the Edit/Create forms
    roles = Role.query.all()
    
    return render_template('manage_users.html', 
                           user=user, 
                           users=users,
                           roles=roles)
@main.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def edit_user(user_id):
    """Admin route to handle updating an existing user's details and role."""
    user_to_edit = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Get data from the edit form
        name = request.form.get('name')
        role_id = request.form.get('role')
        password = request.form.get('password') # Optional password change

        # Update fields
        if name:
            user_to_edit.name = name
        
        if role_id:
            user_to_edit.role_id = role_id
            
        if password:
            # Check if password is not empty before hashing
            if len(password) >= 6: # Assume a minimum length validation
                user_to_edit.set_password(password)
            else:
                flash('Password must be at least 6 characters long to update.', 'warning')
                return redirect(url_for('main.manage_users'))

        try:
            db.session.commit()
            flash(f'User "{user_to_edit.name}" updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating user: {e}', 'danger')

    return redirect(url_for('main.manage_users'))

@main.route('/create_project', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def create_project():
    """Admin route to create a new project with modules and sub-modules."""
    user = g.user
    projects = Project.query.all()
    
    if request.method == 'POST':
        # Check if this is a DELETE request from the list (using a hidden field)
        action = request.form.get('action')
        
        if action == 'delete_project':
            project_id = request.form.get('project_id')
            project_to_delete = Project.query.get(project_id)
            if project_to_delete:
                try:
                    # Cascade delete: Delete all related Modules and SubModules first
                    # NOTE: If your database uses ON DELETE CASCADE, these explicit deletes may be optional.
                    # Otherwise, you MUST delete child objects first.
                    for module in project_to_delete.modules:
                        SubModule.query.filter_by(module_id=module.id).delete()
                        db.session.delete(module)
                        
                    db.session.delete(project_to_delete)
                    db.session.commit()
                    flash(f'Project "{project_to_delete.name}" and all associated data deleted successfully!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred during deletion: {e}', 'danger')
            else:
                flash('Project not found.', 'danger')
            return redirect(url_for('main.create_project'))

        # Original CREATE PROJECT logic (only runs if action is not 'delete_project')
        name = request.form.get('name')
        description = request.form.get('description')
        
        existing_project = Project.query.filter_by(name=name).first()
        if existing_project:
            flash('Project with this name already exists.', 'danger')
            return redirect(url_for('main.create_project'))

        new_project = Project(name=name, description=description)
        db.session.add(new_project)
        
        # ... (rest of your module/sub-module creation logic is unchanged) ...
        
        # Process modules and sub-modules
        for key, value in request.form.items():
            if key.startswith('module_name_'):
                module_index = key.split('_')[2]
                module_name = value
                
                if module_name:
                    new_module = Module(name=module_name, project=new_project)
                    db.session.add(new_module)
                    
                    # Find and process sub-modules for this module
                    for sub_key, sub_value in request.form.items():
                        if sub_key.startswith(f'sub_module_name_{module_index}_'):
                            sub_module_name = sub_value
                            if sub_module_name:
                                new_sub_module = SubModule(name=sub_module_name, module=new_module)
                                db.session.add(new_sub_module)

        db.session.commit()
        
        flash(f'Project "{name}" created successfully with modules!', 'success')
        return redirect(url_for('main.create_project'))
            
    return render_template('create_project.html', user=user, projects=projects)
@main.route('/edit_project/<int:project_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def edit_project(project_id):
    """Admin route to update a project's name and description."""
    project = Project.query.get_or_404(project_id)
    
    # Get form data
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not all([name, description]):
        flash('Project Name and Description are required.', 'danger')
        return redirect(url_for('main.create_project'))

    # Check for duplicate name, excluding the current project
    existing_project = Project.query.filter(Project.name == name, Project.id != project_id).first()
    if existing_project:
        flash('Project with this name already exists.', 'danger')
        return redirect(url_for('main.create_project'))
        
    project.name = name
    project.description = description
    
    try:
        db.session.commit()
        flash(f'Project "{project.name}" updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while updating project: {e}', 'danger')
        
    return redirect(url_for('main.create_project'))
@main.route('/edit_module/<int:module_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def edit_module(module_id):
    """Admin route to edit the name of an existing module."""
    module = Module.query.get_or_404(module_id)
    # project_id = module.project_id # This line is optional, but harmless
    
    new_name = request.form.get('name')
    if not new_name:
        flash('Module name cannot be empty.', 'danger')
        return redirect(url_for('main.create_project'))
        
    module.name = new_name
    
    try:
        db.session.commit()
        flash(f'Module updated to "{new_name}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating module: {e}', 'danger')
        
    return redirect(url_for('main.create_project'))
# --- Add Module to Existing Project (Updated) ---
@main.route('/add_module_to_project/<int:project_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def add_module_to_project(project_id):
    """Admin route to add a new module to an existing project."""
    project = Project.query.get_or_404(project_id)
    module_name = request.form.get('name')
    
    if not module_name:
        flash('Module name cannot be empty.', 'danger')
        return redirect(url_for('main.create_project'))

    try:
        new_module = Module(name=module_name, project_id=project_id)
        db.session.add(new_module)
        db.session.commit()
        flash(f'New Module "{module_name}" added to project "{project.name}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding module: {e}', 'danger')
        
    return redirect(url_for('main.create_project'))


# --- Add Submodule to Existing Module (Updated) ---
@main.route('/add_submodule_to_module/<int:module_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def add_submodule_to_module(module_id):
    """Admin route to add a new submodule to an existing module."""
    module = Module.query.get_or_404(module_id)
    submodule_name = request.form.get('name')
    
    if not submodule_name:
        flash('Submodule name cannot be empty.', 'danger')
        return redirect(url_for('main.create_project')) 

    try:
        new_submodule = SubModule(name=submodule_name, module_id=module_id)
        db.session.add(new_submodule)
        db.session.commit()
        flash(f'New Submodule "{submodule_name}" added to module "{module.name}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding submodule: {e}', 'danger')
        
    return redirect(url_for('main.create_project'))

# --- Delete Module (FIXED: Removed '/admin' prefix) ---
@main.route('/delete_module/<int:module_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def delete_module(module_id):
    """Deletes a module and all associated submodules."""
    module = Module.query.get_or_404(module_id)
    project_id = module.project_id
    
    try:
        # Delete related SubModules
        SubModule.query.filter_by(module_id=module.id).delete()
        db.session.delete(module)
        db.session.commit()
        flash(f'Module "{module.name}" and all submodules deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting module: {e}', 'danger')
        
    return redirect(url_for('main.create_project')) 

# --- Edit Submodule (FIXED: Removed '/admin' prefix) ---
@main.route('/edit_submodule/<int:submodule_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def edit_submodule(submodule_id):
    """Admin route to edit the name of an existing submodule."""
    submodule = SubModule.query.get_or_404(submodule_id)
    
    new_name = request.form.get('name')
    if not new_name:
        flash('SubModule name cannot be empty.', 'danger')
        return redirect(url_for('main.create_project'))
        
    submodule.name = new_name
    
    try:
        db.session.commit()
        flash(f'SubModule updated to "{new_name}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating submodule: {e}', 'danger')
        
    return redirect(url_for('main.create_project')) 

# --- Delete Submodule (FIXED: Removed '/admin' prefix) ---
@main.route('/delete_submodule/<int:submodule_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def delete_submodule(submodule_id):
    """Deletes a submodule."""
    submodule = SubModule.query.get_or_404(submodule_id)
    
    try:
        db.session.delete(submodule)
        db.session.commit()
        flash(f'SubModule "{submodule.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting submodule: {e}', 'danger')
        
    return redirect(url_for('main.create_project'))

# --- Manage Project Assignments (ALREADY CORRECT) ---
@main.route('/manage_project_assignments', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def manage_project_assignments():
    """Admin route to manage user assignments to projects and display current assignments."""
    user = g.user
    
    # Data for the Assignment Form (Select Project, Select Users)
    projects = Project.query.order_by(Project.name).all()
    devs_and_pms = User.query.join(Role).filter(Role.name.in_(['Project Head', 'Developer'])).order_by(User.name).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id')
        user_ids = request.form.getlist('user_ids') 
        project = Project.query.get(project_id)
        
        if not project:
            flash('Project not found.', 'danger')
            return redirect(url_for('main.manage_project_assignments'))

        try:
            assigned_users = User.query.filter(User.id.in_(user_ids)).all()
            project.users = assigned_users 
            db.session.commit()
            flash(f'Assignments for project "{project.name}" updated successfully.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while saving assignments: {e}', 'danger')

        return redirect(url_for('main.manage_project_assignments'))

    # --- GET REQUEST: Fetch Data for Display List ---
    
    assigned_projects = Project.query.options(
        joinedload(Project.users).joinedload(User.role) 
    ).order_by(Project.name).all()

    return render_template('manage_project_assignments.html', 
                           user=user, 
                           projects=projects,
                           devs_and_pms=devs_and_pms,
                           assigned_projects=assigned_projects)

@main.route('/delete_project/<int:project_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def delete_project(project_id):
    """API endpoint to delete a project."""
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Project deleted successfully.'}), 200


@main.route('/delete_sub_module/<int:sub_module_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def delete_sub_module(sub_module_id):
    """API endpoint to delete a sub-module."""
    sub_module = SubModule.query.get_or_404(sub_module_id)
    db.session.delete(sub_module)
    db.session.commit()
    return jsonify({'message': 'Sub-module deleted successfully.'}), 200

@main.route('/report_bug', methods=['GET'])
@login_required
@permission_required(allowed_roles=['Tester', 'Testing Head'])
def report_bug():
    """Renders the single/bulk bug report form, filtering initial status options by user role type.
       Only shows releases where testing has been started (testing_started=True) for bug reporting."""
    user = g.user
    
    # 1. Determine the user's role type for status filtering (should be 'TESTER' or 'ALL')
    user_role_type = _get_role_type_for_user(user)

    # 2. Filter statuses: only include statuses that are 'ALL' or match the user's specific role type
    statuses = Status.query.filter(
        db.or_(
            Status.role_type == 'ALL',
            Status.role_type == user_role_type
        )
    ).all()

    # DEBUG: Print all assigned releases before filtering
    print(f"DEBUG - User {user.username} has {len(user.assigned_releases)} total assigned releases")
    for r in user.assigned_releases:
        print(f"DEBUG - Assigned release: {r.version_number}, Status: {r.status}, is_active: {r.is_active}, testing_started: {r.testing_started}")
    
    # Only show releases where testing has been started
    # FILTER: status='active', is_active=True, AND testing_started=True
    assigned_releases = [r for r in user.assigned_releases if r.status == 'active' and r.is_active and r.testing_started]
    
    print(f"DEBUG - After filtering: {len(assigned_releases)} releases with testing started")
    for r in assigned_releases:
        print(f"DEBUG - Release ready for testing: {r.version_number}, testing_started: {r.testing_started}")
    
    # Retrieve projects associated with the assigned releases
    if assigned_releases:
        release_ids = [r.id for r in assigned_releases]
        projects = Project.query.filter(Project.releases.any(Release.id.in_(release_ids))).all()
    else:
        projects = []
    
    priorities = Priority.query.all()
    
    # Already correctly filters assignable users for the initial report form
    assignable_users = User.query.join(Role).filter(Role.name.in_(['Project Head', 'Developer'])).all()
        
    # Prepare the data in a dictionary to be passed to the template
    server_data = {
        "allProjects": [{"id": p.id, "name": p.name} for p in projects],
        "allReleases": [{"id": r.id, "version_number": r.version_number} for r in assigned_releases],
        "allPriorities": [{"id": p.id, "name": p.name} for p in priorities],
        "allAssignableUsers": [{"id": u.id, "username": u.username} for u in assignable_users],
        # Only sending filtered statuses to the frontend
        "allStatuses": [{"id": s.id, "name": s.name} for s in statuses],
        # Add counts for debugging in template
        "debug": {
            "total_releases": len(user.assigned_releases),
            "testing_started_releases": len(assigned_releases)
        }
    }
    
    return render_template('report_bug.html', 
                           title='Report a Bug',
                           user=user,
                           server_data=server_data)

@main.route('/report_bug_list', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Tester', 'Testing Head'])
def report_bug_list():
    """API endpoint to handle bulk bug submission from the client (including Base64 screenshots),
    with server-side validation for initial status based on role type and active release check."""
    user = g.user
    user_role_type = _get_role_type_for_user(user)
    bug_reports = request.get_json()
    
    if not bug_reports:
        return jsonify({'error': 'No bugs provided'}), 400

    try:
        for bug_data in bug_reports:
            # --- PHASE 1: Data Parsing and Bug Creation ---
            title = bug_data.get('title')
            description = bug_data.get('description')
            project_id = bug_data.get('project_id')
            release_id = bug_data.get('release_id')
            module_id = bug_data.get('module_id')
            sub_module_id = bug_data.get('sub_module_id')
            priority_id = bug_data.get('priority_id')
            assigned_to_id = bug_data.get('assigned_to_id')
            status_id = bug_data.get('status_id')
            
            if not all([title, project_id, release_id, priority_id, assigned_to_id, status_id]):
                print("Skipping bug due to missing essential fields.")
                continue
            
            # VALIDATION 1: Check if the release exists and is ACTIVE (status='active' AND is_active=True)
            release = Release.query.get(release_id)
            if not release:
                return jsonify({'error': f'Release with ID {release_id} not found.'}), 404
            
            # STRICT VALIDATION: Release must be active for bug reporting
            if release.status != 'active' or not release.is_active:
                return jsonify({
                    'error': f'Cannot add bugs to release {release.version_number}. ' +
                            f'Release must be ACTIVE. Current status: {release.status}, ' +
                            f'Active flag: {release.is_active}'
                }), 403
            
            # VALIDATION 2: Check if the user is assigned to this release
            if user not in release.assigned_users:
                return jsonify({
                    'error': f'You are not assigned to release {release.version_number}. ' +
                            'Only assigned testers can report bugs.'
                }), 403
            
            status = Status.query.get(status_id)
            if not status:
                return jsonify({'error': f'Invalid status ID provided: {status_id}'}), 400
            
            # VALIDATION 3: Check if the user is authorized to use this initial status
            if status.role_type != 'ALL' and status.role_type != user_role_type:
                return jsonify({
                    'error': f'Unauthorized status: {status.name} for initial bug report. ' +
                            f'Your role type is {user_role_type}, required role type is {status.role_type}'
                }), 403

            bug = Bug(
                title=title,
                description=description,
                project_id=project_id,
                module_id=module_id,
                sub_module_id=sub_module_id,
                priority_id=priority_id,
                status=status,
                reporter_id=user.id,
                assigned_to_id=assigned_to_id,
                release_id=release_id
            )
            db.session.add(bug)
            db.session.flush() # Flush to get the bug ID

            # --- PHASE 2: Screenshot Handling with Detailed Debugging (Base64) ---
            screenshot_data = bug_data.get('screenshot')
            if screenshot_data:
                try:
                    print(f"--- SCREENSHOT DEBUG for Bug ID: {bug.id} ---")
                    
                    if not screenshot_data.startswith('data:image'):
                        print("!!! ERROR: Screenshot data missing data URI header.")
                        continue
                        
                    header, encoded = screenshot_data.split(',', 1)
                    print(f"DEBUG: Header extracted: {header}")

                    data = b64decode(encoded)
                    print(f"DEBUG: Base64 decoding successful. Data size: {len(data)} bytes")
                    
                    mime_type = header.split(';')[0].split(':')[1]
                    ext = mime_type.split('/')[1] if '/' in mime_type else 'png'  # Default to png
                    print(f"DEBUG: MIME Type: {mime_type}, Extension: {ext}")
                    
                    filename = secure_filename(f'bug_{bug.id}_screenshot.{ext}')
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    print(f"DEBUG: Calculated Filename: {filename}")
                    print(f"DEBUG: Full Save Path: {file_path}")
                    
                    with open(file_path, 'wb') as f:
                        f.write(data)
                    print(f"DEBUG: File successfully written to disk.")
                    
                    screenshot = BugScreenshot(bug_id=bug.id, file_path=filename) 
                    db.session.add(screenshot)
                    print("DEBUG: Database record for screenshot added.")

                except Exception as file_e:
                    print("!!! CRITICAL FILE ERROR DURING SCREENSHOT PROCESSING !!!")
                    print(f"Error for Bug ID {bug.id}: {file_e}")
                    traceback.print_exc()
                    continue

        db.session.commit()
        
        # Emit a WebSocket event for real-time notification (using the last created bug's data)
        if 'bug' in locals():
            # Get the project name for the notification
            project_name = bug.project.name if bug.project else 'Unknown Project'
            reporter_name = bug.reporter.name if bug.reporter else 'Unknown User'
            
            socketio.emit('new_bug_report', {
                'title': bug.title,
                'reporter_name': reporter_name,
                'project_name': project_name,
                'release_version': release.version_number if release else 'Unknown Release'
            }, namespace='/')
            
            print(f"DEBUG: New bug report notification sent - {bug.title}")

    except Exception as e:
        db.session.rollback()
        print(f"!!! FATAL ERROR during bug submission/DB transaction: {e}") 
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    return jsonify({'message': 'Bugs submitted successfully', 'count': len(bug_reports)}), 200


@main.route('/get_modules/<int:project_id>')
@login_required
def get_modules(project_id):
    """API endpoint to get modules for a project."""
    modules = Module.query.filter_by(project_id=project_id).all()
    modules_data = [{'id': m.id, 'name': m.name} for m in modules]
    return jsonify(modules_data)

@main.route('/start_testing/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Tester', 'Testing Head'])
def start_testing(release_id):
    """Tester starts testing a release - marks it as ready for bug reporting."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # Check if release is in correct state
    if release.status != 'active':
        flash('This release is not available for testing.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Check if the user is assigned to this release
    if user not in release.assigned_users:
        flash('You are not assigned to this release.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Mark testing as started
    release.testing_started = True
    
    db.session.commit()
    
    flash(f'✅ Started testing on release {release.version_number}. You can now report bugs!', 'success')
    return redirect(url_for('main.dashboard'))

@main.route('/get_sub_modules/<int:module_id>')
@login_required
def get_sub_modules(module_id):
    """API endpoint to get sub-modules for a module."""
    sub_modules = SubModule.query.filter_by(module_id=module_id).all()
    sub_modules_data = [{'id': s.id, 'name': s.name} for s in sub_modules]
    return jsonify(sub_modules_data)

@main.route("/get_releases/<int:project_id>")
@login_required
def get_releases(project_id):
    """API endpoint to get releases for a project, filtered by the current user's assignment.
       Only returns releases where testing has been started (testing_started=True)"""
    
    # STRICT FILTERING: Only return releases where testing has started
    # Must have status='active', is_active=True, AND testing_started=True
    releases = Release.query.filter(
        Release.project_id == project_id,
        Release.assigned_users.any(User.id == g.user.id),
        Release.status == 'active',      # Must have status 'active'
        Release.is_active == True,        # Must be marked as active
        Release.testing_started == True   # MUST have testing started
    ).order_by(Release.timestamp.desc()).all()
    
    # Debug logging to help troubleshoot
    print(f"DEBUG: Found {len(releases)} releases with testing started for project ID {project_id} and user {g.user.id}")
    
    # Log each release found for debugging
    for release in releases:
        print(f"DEBUG: Release ready for testing - ID: {release.id}, Version: {release.version_number}, Status: {release.status}, is_active: {release.is_active}, testing_started: {release.testing_started}")
    
    release_data = [{'id': r.id, 'version_number': r.version_number} for r in releases]
    return jsonify(releases=release_data)


@main.route('/release_build', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin', 'Project Head', 'Developer', 'Testing Head', 'Tester'])
def release_build():
    """Handles the creation and management of build releases with full lifecycle support."""
    user = g.user
    
    # Filter projects based on user assignment (or all for Admin)
    if user.role.name == 'Admin':
        assigned_projects = Project.query.all()
    elif user.role.name in ['Project Head', 'Developer']:
        assigned_projects = user.projects
    elif user.role.name in ['Testing Head', 'Tester']:
        # Testers see projects from their assigned releases
        release_projects = set()
        for release in user.assigned_releases:
            release_projects.add(release.project)
        assigned_projects = list(release_projects)
    else:
        assigned_projects = []
    
    # Find all users who are testers (for assignment)
    testers = User.query.join(Role).filter(Role.name.in_(['Tester', 'Testing Head'])).all()
    
    if request.method == 'POST':
        action = request.form.get('action', 'create_release')
        
        # Handle different actions
        if action == 'create_release':
            project_id = request.form.get('project_id')
            version_number = request.form.get('version_number')
            release_note = request.form.get('release_note')
            tester_ids = request.form.getlist('testers')
            
            # Check for unique version number within the selected project
            existing_release = Release.query.filter_by(project_id=project_id, version_number=version_number).first()
            if existing_release:
                flash(f'Version {version_number} already exists for this project.', 'danger')
                return redirect(url_for('main.release_build'))
                
            new_release = Release(
                version_number=version_number, 
                release_note=release_note,
                released_by_id=user.id,
                project_id=project_id,
                status='active',
                is_active=True,
                testing_started=False  # New releases start with testing not started
            )
            
            # Assign selected testers to the new release
            for tester_id in tester_ids:
                tester = User.query.get(tester_id)
                if tester:
                    new_release.assigned_users.append(tester)
            
            db.session.add(new_release)
            db.session.commit()
            
            flash(f'✅ Build version {version_number} for project {new_release.project.name} released successfully!', 'success')
            return redirect(url_for('main.release_build'))
    
    # Get all releases with filtering based on user role
    if user.role.name == 'Admin':
        releases = Release.query.order_by(Release.timestamp.desc()).all()
    elif user.role.name in ['Project Head', 'Developer']:
        # Developers see releases from their projects
        project_ids = [p.id for p in user.projects]
        releases = Release.query.filter(Release.project_id.in_(project_ids)).order_by(Release.timestamp.desc()).all()
    elif user.role.name in ['Testing Head', 'Tester']:
        # Testers see releases they're assigned to
        releases = user.assigned_releases
    else:
        releases = []
    
    # Add status colors and badges for template
    status_colors = {
        'active': 'bg-green-100 text-green-800',
        'reported': 'bg-orange-100 text-orange-800',
        'submitted_by_tester': 'bg-yellow-100 text-yellow-800',
        'in_progress': 'bg-blue-100 text-blue-800',
        'ready_for_testing': 'bg-purple-100 text-purple-800',
        'closed': 'bg-gray-100 text-gray-800'
    }
    
    status_labels = {
        'active': '🟢 Active - Testers can add bugs',
        'reported': '🟠 Reported - Locked, ready for developers',
        'submitted_by_tester': '🟡 Submitted by Testing Head - Ready for Devs',
        'in_progress': '🔵 In Progress - Developers fixing bugs',
        'ready_for_testing': '🟣 Ready for Testing - Testers verify',
        'closed': '⚫ Closed - Release completed'
    }
    
    return render_template('release_build.html', 
                          user=user, 
                          assigned_projects=assigned_projects, 
                          releases=releases, 
                          testers=testers,
                          status_colors=status_colors,
                          status_labels=status_labels)


@main.route('/report_build/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Testing Head'])
def report_build(release_id):
    """Testing Head reports the build - locks it so no more bugs can be added."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # Check if release is in correct state (must be 'active')
    if release.status != 'active':
        flash(f'This release cannot be reported. Current status: {release.status}', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if testing has started
    if not release.testing_started:
        flash('Please start testing before reporting the build.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Check if there are any bugs to report
    if release.get_all_bugs_count() == 0:
        flash('Cannot report build with no bugs. Please add bugs first.', 'danger')
        return redirect(url_for('main.report_bug'))
    
    # Update release status to 'reported' (locked for testers, pending for developers)
    release.status = 'reported'
    release.is_active = False  # Testers can no longer add bugs
    release.submitted_by_tester_id = user.id
    release.submitted_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'✅ Build {release.version_number} reported to developers! No more bugs can be added. Developers can now start working on it.', 'success')
    return redirect(url_for('main.release_build'))

@main.route('/submit_release_as_tester/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Testing Head'])
def submit_release_as_tester(release_id):
    """Testing Head submits a release after adding all bugs."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # Check if release is in correct state
    if release.status != 'active':
        flash('This release cannot be submitted at this stage.', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Update release status
    release.status = 'submitted_by_tester'
    release.submitted_by_tester_id = user.id
    release.submitted_at = datetime.utcnow()
    release.is_active = False  # Testers can no longer add bugs
    
    db.session.commit()
    
    flash(f'Release {release.version_number} submitted to developers successfully!', 'success')
    return redirect(url_for('main.release_build'))


@main.route('/start_development/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Developer', 'Project Head'])
def start_development(release_id):
    """Developer starts working on the release - only allowed after testing head reports it."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # STRICT CHECK: Only allow starting development if release is reported/submitted
    if release.status not in ['reported', 'submitted_by_tester']:
        status_display = {
            'active': 'Active (Testing not started)',
            'reported': 'Reported (Ready for development)',
            'submitted_by_tester': 'Submitted by Tester (Ready for development)',
            'in_progress': 'In Progress (Already in development)',
            'ready_for_testing': 'Ready for Testing',
            'closed': 'Closed'
        }.get(release.status, release.status)
        
        flash(f'⚠️ Cannot start development. Release "{release.version_number}" must first be reported/submitted by Testing Head. Current status: {status_display}', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if there are any bugs in this release
    if release.get_all_bugs_count() == 0:
        flash(f'⚠️ Cannot start development. Release "{release.version_number}" has no bugs to fix.', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Update release status to in_progress
    release.status = 'in_progress'
    db.session.commit()
    
    bug_count = release.get_all_bugs_count()
    open_bugs = release.get_open_bugs_count()
    
    flash(f'✅ Started working on release {release.version_number} - {bug_count} total bugs, {open_bugs} open bugs to fix', 'success')
    return redirect(url_for('main.view_bugs', project_id=release.project_id))

@main.route('/submit_release_as_developer/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Developer', 'Project Head'])
def submit_release_as_developer(release_id):
    """Developer submits release after fixing bugs and creates new release.
       Copies ALL bugs to the new release with their current status.
       Automatically closes the current release and creates a new active release."""
    user = g.user
    current_release = Release.query.get_or_404(release_id)
    
    # Check if release is in correct state
    if current_release.status != 'in_progress':
        flash('This release is not ready for submission.', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if at least one bug is fixed
    fixed_bugs = current_release.get_closed_bugs_count()
    if fixed_bugs == 0:
        flash('Cannot publish: No bugs have been fixed yet. Please fix at least one bug first.', 'danger')
        return redirect(url_for('main.view_bugs', project_id=current_release.project_id))
    
    # Auto-generate new version number
    current_version = current_release.version_number
    if '-' in current_version:
        base, build = current_version.split('-')
        try:
            new_build = int(build) + 1
            new_version = f"{base}-{new_build:02d}"
        except (ValueError, TypeError):
            new_version = f"{current_version}-next"
    else:
        new_version = f"{current_version}-01"
    
    # Create new release based on current one
    new_release = Release(
        version_number=new_version,
        released_by_id=user.id,
        release_note=f"Auto-created from release {current_release.version_number} ({fixed_bugs} bugs fixed)",
        project_id=current_release.project_id,
        is_active=True,
        status='active',  # New release starts as active
        parent_release_id=current_release.id,
        testing_started=False  # Testing hasn't started on new release yet
    )
    
    # Add the new release to session and flush to get its ID
    db.session.add(new_release)
    db.session.flush()
    
    # Copy assigned testers from parent release
    for tester in current_release.assigned_users:
        if tester.role.name in ['Tester', 'Testing Head']:
            new_release.assigned_users.append(tester)
    
    # Track counts for feedback
    total_bugs = 0
    
    # COPY ALL BUGS to new release with their CURRENT STATUS
    for bug in current_release.bugs:
        new_bug = Bug(
            title=bug.title,
            description=bug.description,
            project_id=bug.project_id,
            module_id=bug.module_id,
            sub_module_id=bug.sub_module_id,
            priority_id=bug.priority_id,
            status_id=bug.status_id,
            reporter_id=bug.reporter_id,
            assigned_to_id=bug.assigned_to_id,
            release_id=new_release.id
        )
        db.session.add(new_bug)
        total_bugs += 1
        
        # Add history entry for the copied bug
        history = BugHistory(
            bug=new_bug,
            user_id=user.id,
            change_description=f"Bug moved to new release {new_release.version_number} with status {bug.status.name}"
        )
        db.session.add(history)
        
        # Add note to original bug history
        if bug.status.name in ['Closed', 'Resolved', 'Verified', 'Done']:
            history_original = BugHistory(
                bug=bug,
                user_id=user.id,
                change_description=f"Bug fixed in release {current_release.version_number} and copied to new release {new_release.version_number} for verification"
            )
            db.session.add(history_original)
    
    # CLOSE THE CURRENT RELEASE (instead of setting to ready_for_testing)
    current_release.status = 'closed'
    current_release.submitted_by_developer_id = user.id
    current_release.submitted_at = datetime.utcnow()
    current_release.completed_at = datetime.utcnow()
    
    # Commit everything
    db.session.commit()
    
    # Success message with details
    flash(f'✅ Release {current_release.version_number} completed and closed! ' + 
          f'<strong>{fixed_bugs}</strong> bug(s) fixed, ' +
          f'<strong>{total_bugs}</strong> total bug(s) copied to new release ' +
          f'<strong>{new_version}</strong>. Testers can now start testing the new release.', 'success')
    
    return redirect(url_for('main.release_build'))


@main.route('/close_release/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Tester', 'Testing Head'])
def close_release(release_id):
    """Tester closes a release after verification."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # Check if release is ready for testing
    if release.status != 'ready_for_testing':
        flash(f'This release cannot be closed. It is not in ready_for_testing state. Current status: {release.status}', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if all bugs are verified/closed
    open_bugs = release.get_open_bugs_count()
    if open_bugs > 0:
        flash(f'Cannot close release. There are {open_bugs} bugs that are still open/not verified.', 'danger')
        return redirect(url_for('main.view_bugs', project_id=release.project_id))
    
    # Close the release
    release.status = 'closed'
    release.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'✅ Release {release.version_number} has been closed successfully!', 'success')
    return redirect(url_for('main.release_build'))

@main.route('/close_release_by_testing_head/<int:release_id>', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Testing Head'])
def close_release_by_testing_head(release_id):
    """Testing Head closes a release after all bugs are verified."""
    user = g.user
    release = Release.query.get_or_404(release_id)
    
    # Check if release is active and testing has started
    if release.status != 'active':
        flash(f'This release cannot be closed. Current status: {release.status}', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if testing has started
    if not release.testing_started:
        flash('Testing has not started on this release yet.', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Check if all bugs are verified/closed
    open_bugs = release.get_open_bugs_count()
    if open_bugs > 0:
        flash(f'Cannot close release. There are {open_bugs} bugs that are still open/not verified.', 'danger')
        return redirect(url_for('main.view_bugs', project_id=release.project_id))
    
    # Check if there are any bugs at all
    if release.get_all_bugs_count() == 0:
        flash('Cannot close release with no bugs. Please add bugs first or delete this release.', 'danger')
        return redirect(url_for('main.release_build'))
    
    # Close the release
    release.status = 'closed'
    release.completed_at = datetime.utcnow()
    release.is_active = False
    
    db.session.commit()
    
    flash(f'✅ Release {release.version_number} has been closed successfully! All bugs have been verified.', 'success')
    return redirect(url_for('main.release_build'))

@main.route('/release_details/<int:release_id>')
@login_required
def release_details(release_id):
    """Get details for a specific release (API endpoint) with comprehensive history."""
    release = Release.query.get_or_404(release_id)
    
    # Get user role for permission checks
    user_role = g.user.role.name if g.user and g.user.role else None
    
    # Calculate timeline data
    timeline = []
    
    # Release Created
    timeline.append({
        'timestamp': release.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'event': 'Release Created',
        'user': release.released_by.name if release.released_by else 'System',
        'details': f'Version {release.version_number} created'
    })
    
    # Testing Started - check if any bugs exist or if testing_started flag is True
    if release.testing_started:
        # Sort bugs by timestamp to find the first one
        bugs_list = list(release.bugs)
        if bugs_list:
            bugs_list.sort(key=lambda x: x.timestamp)
            first_bug = bugs_list[0]
            timeline.append({
                'timestamp': first_bug.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'event': 'Testing Started',
                'user': first_bug.reporter.name if first_bug.reporter else 'Tester',
                'details': 'Testing phase initiated'
            })
    elif release.bugs:
        # If there are bugs but testing_started is False, add a note
        bugs_list = list(release.bugs)
        bugs_list.sort(key=lambda x: x.timestamp)
        first_bug = bugs_list[0]
        timeline.append({
            'timestamp': first_bug.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'First Bug Reported',
            'user': first_bug.reporter.name if first_bug.reporter else 'Tester',
            'details': 'First bug reported in this release'
        })
    
    # Bugs Reported (grouped by date)
    bugs_by_date = {}
    for bug in release.bugs:
        date_key = bug.timestamp.strftime('%Y-%m-%d')
        if date_key not in bugs_by_date:
            bugs_by_date[date_key] = 0
        bugs_by_date[date_key] += 1
    
    for date, count in bugs_by_date.items():
        timeline.append({
            'timestamp': date,
            'event': 'Bugs Reported',
            'user': 'Testers',
            'details': f'{count} bug(s) reported on this day'
        })
    
    # Reported to Developers (Testing Head)
    if release.submitted_by_tester_id:
        timeline.append({
            'timestamp': release.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if release.submitted_at else 'Unknown',
            'event': 'Reported to Developers',
            'user': release.submitted_by_tester.name if release.submitted_by_tester else 'Testing Head',
            'details': 'Build reported to development team'
        })
    
    # Development Started - Look through bug histories
    dev_started = False
    for bug in release.bugs:
        for history in bug.history:
            if 'Status changed from' in history.change_description and 'reported' in history.change_description.lower() and 'in_progress' in history.change_description.lower():
                timeline.append({
                    'timestamp': history.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'event': 'Development Started',
                    'user': history.user.name,
                    'details': 'Developer started working on bugs'
                })
                dev_started = True
                break
        if dev_started:
            break
    
    # If development started but not captured, check for any status changes from reported
    if not dev_started and release.status in ['in_progress', 'ready_for_testing', 'closed']:
        for bug in release.bugs:
            for history in bug.history:
                if 'Status changed from' in history.change_description and 'reported' in history.change_description.lower():
                    timeline.append({
                        'timestamp': history.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                        'event': 'Development Started',
                        'user': history.user.name,
                        'details': 'Developer started working on bugs'
                    })
                    dev_started = True
                    break
            if dev_started:
                break
    
    # Bug Status Changes by Developer - Collect from all bugs in this release
    dev_changes = []
    for bug in release.bugs:
        for history in bug.history:
            if 'Status changed from' in history.change_description:
                dev_changes.append({
                    'timestamp': history.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'user': history.user.name,
                    'change': history.change_description,
                    'bug_title': bug.title,
                    'bug_id': bug.id
                })
    
    # Sort dev_changes by timestamp
    dev_changes.sort(key=lambda x: x['timestamp'])
    
    # Published by Developer
    if release.submitted_by_developer_id:
        timeline.append({
            'timestamp': release.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if release.submitted_at else 'Unknown',
            'event': 'Published by Developer',
            'user': release.submitted_by_developer.name if release.submitted_by_developer else 'Developer',
            'details': 'Release published, new version created'
        })
    
    # Closed
    if release.completed_at:
        timeline.append({
            'timestamp': release.completed_at.strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'Release Closed',
            'user': release.submitted_by_developer.name if release.submitted_by_developer else 'System',
            'details': 'Release completed and closed'
        })
    
    # Add current status event if release is in progress
    if release.status == 'in_progress' and not release.submitted_by_developer_id:
        timeline.append({
            'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'Currently In Development',
            'user': 'System',
            'details': 'Developer is actively working on fixing bugs'
        })
    elif release.status == 'active' and release.testing_started:
        timeline.append({
            'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'Currently Testing',
            'user': 'System',
            'details': 'Testers are actively testing the release'
        })
    elif release.status == 'active' and not release.testing_started:
        timeline.append({
            'timestamp': release.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'event': 'Awaiting Testing',
            'user': 'System',
            'details': 'Release created, waiting for testing to start'
        })
    
    # Sort timeline by timestamp
    timeline.sort(key=lambda x: x['timestamp'])
    
    # Parent Release Info
    parent_info = None
    if release.parent_release:
        parent_info = {
            'id': release.parent_release.id,
            'version_number': release.parent_release.version_number,
            'status': release.parent_release.status,
            'total_bugs': release.parent_release.get_all_bugs_count(),
            'closed_bugs': release.parent_release.get_closed_bugs_count(),
            'created_at': release.parent_release.timestamp.strftime('%Y-%m-%d %H:%M:%S') if release.parent_release.timestamp else None
        }
    
    # Child Releases Info
    child_info = []
    for child in release.child_releases:
        child_info.append({
            'id': child.id,
            'version_number': child.version_number,
            'status': child.status,
            'total_bugs': child.get_all_bugs_count(),
            'closed_bugs': child.get_closed_bugs_count(),
            'created_at': child.timestamp.strftime('%Y-%m-%d %H:%M:%S') if child.timestamp else None
        })
    
    # Bug Status Breakdown
    status_breakdown = {}
    for bug in release.bugs:
        status_name = bug.status.name
        status_breakdown[status_name] = status_breakdown.get(status_name, 0) + 1
    
    data = {
        'id': release.id,
        'project_id': release.project_id,  # <-- ADDED: Required for navigation
        'version_number': release.version_number,
        'status': release.status,
        'status_display': release.status.replace('_', ' ').title(),
        'is_active': release.is_active,
        'testing_started': release.testing_started,
        'total_bugs': release.get_all_bugs_count(),
        'open_bugs': release.get_open_bugs_count(),
        'closed_bugs': release.get_closed_bugs_count(),
        'publish_ready_count': release.get_publish_ready_count(),
        'publish_progress': release.get_publish_progress(),
        'progress': release.get_testing_progress(),
        'timeline': timeline,
        'dev_changes': dev_changes,
        'status_breakdown': status_breakdown,
        'parent_info': parent_info,
        'child_info': child_info,
        'can_testers_add': release.can_testers_add_bugs(),
        'can_developers_edit': release.can_developers_edit(),
        'can_testing_head_submit': release.can_testing_head_submit() if user_role == 'Testing Head' else False,
        'can_developer_submit': release.can_developer_submit() if user_role in ['Developer', 'Project Head'] else False,
        'can_report_build': release.status == 'active' and release.get_all_bugs_count() > 0 if user_role == 'Testing Head' else False,
        'can_start_development': release.status in ['submitted_by_tester', 'reported'] if user_role in ['Developer', 'Project Head'] else False,
        'can_publish': release.can_publish() if user_role in ['Developer', 'Project Head'] else False,
        'can_close': release.status == 'ready_for_testing' if user_role in ['Tester', 'Testing Head'] else False,
        'created_by': release.released_by.name if release.released_by else 'Unknown',
        'created_at': release.timestamp.strftime('%Y-%m-%d %H:%M') if release.timestamp else None,
        'submitted_at': release.submitted_at.strftime('%Y-%m-%d %H:%M') if release.submitted_at else None,
        'completed_at': release.completed_at.strftime('%Y-%m-%d %H:%M') if release.completed_at else None,
    }
    
    # Add assigned testers info
    data['assigned_testers'] = [{
        'id': tester.id,
        'name': tester.name,
        'username': tester.username
    } for tester in release.assigned_users]
    
    return jsonify(data)


@main.route('/create_status_priority', methods=['GET'])
@login_required
@permission_required(allowed_roles=['Admin'])
def create_status_priority():
    """Renders the page to manage static data (Statuses and Priorities), including role_type."""
    user = g.user
    statuses = Status.query.all()
    priorities = Priority.query.all()
    role_type_options = ['ALL', 'DEVELOPER', 'TESTER'] 
    return render_template('create_static_data.html', 
                           user=user, 
                           statuses=statuses, 
                           priorities=priorities,
                           role_type_options=role_type_options)

@main.route('/admin/status_flows', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def manage_status_flows():
    """Admin route to manage status transitions."""
    user = g.user
    statuses = Status.query.all()
    transitions = StatusTransition.query.all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_transition':
            from_status_id = request.form.get('from_status_id')
            to_status_id = request.form.get('to_status_id')
            allowed_roles = ','.join(request.form.getlist('allowed_roles'))
            
            existing = StatusTransition.query.filter_by(
                from_status_id=from_status_id,
                to_status_id=to_status_id
            ).first()
            
            if existing:
                existing.allowed_role_types = allowed_roles
                flash('Transition updated successfully!', 'success')
            else:
                transition = StatusTransition(
                    from_status_id=from_status_id,
                    to_status_id=to_status_id,
                    allowed_role_types=allowed_roles
                )
                db.session.add(transition)
                flash('Transition added successfully!', 'success')
            
            db.session.commit()
            
        elif action == 'delete_transition':
            transition_id = request.form.get('transition_id')
            transition = StatusTransition.query.get(transition_id)
            if transition:
                db.session.delete(transition)
                db.session.commit()
                flash('Transition deleted successfully!', 'success')
        
        return redirect(url_for('main.manage_status_flows'))
    
    return render_template('manage_status_flows.html', 
                          user=user, 
                          statuses=statuses, 
                          transitions=transitions,
                          role_options=['ALL', 'DEVELOPER', 'TESTER'])

@main.route('/add_status', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def add_status():
    """Handles adding a new status, now requiring and saving the role_type."""
    if request.method == 'POST':
        name = request.form.get('status_name')
        role_type = request.form.get('role_type')

        if not name or not role_type:
            flash('Status name and Role Type are required.', 'danger')
            return redirect(url_for('main.create_status_priority'))
            
        existing_status = Status.query.filter_by(name=name).first()
        if existing_status:
            flash(f'Status "{name}" already exists.', 'danger')
        else:
            new_status = Status(name=name, role_type=role_type)
            db.session.add(new_status)
            db.session.commit()
            flash(f'Status "{name}" ({role_type}) created successfully!', 'success')
            
    return redirect(url_for('main.create_status_priority'))

@main.route('/add_priority', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def add_priority():
    """Handles adding a new priority."""
    if request.method == 'POST':
        name = request.form.get('priority_name')
        existing_priority = Priority.query.filter_by(name=name).first()
        if existing_priority:
            flash(f'Priority "{name}" already exists.', 'danger')
        else:
            new_priority = Priority(name=name)
            db.session.add(new_priority)
            db.session.commit()
            flash(f'Priority "{name}" created successfully!', 'success')
    return redirect(url_for('main.create_status_priority'))

@main.route('/admin/status_config', methods=['GET', 'POST'])
@login_required
@permission_required(allowed_roles=['Admin'])
def status_config():
    """Admin route to configure statuses and publish triggers."""
    user = g.user
    statuses = Status.query.all()
    transitions = StatusTransition.query.all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_status':
            name = request.form.get('name')
            role_type = request.form.get('role_type')
            is_final = request.form.get('is_final') == 'on'
            is_closed = request.form.get('is_closed') == 'on'
            color = request.form.get('color', 'gray')
            description = request.form.get('description')
            
            if not name or not role_type:
                flash('Status name and role type are required.', 'danger')
                return redirect(url_for('main.status_config'))
            
            existing = Status.query.filter_by(name=name).first()
            if existing:
                flash(f'Status "{name}" already exists.', 'danger')
            else:
                status = Status(
                    name=name,
                    role_type=role_type,
                    is_final_status=is_final,
                    is_closed_status=is_closed,
                    color=color,
                    description=description
                )
                db.session.add(status)
                db.session.commit()
                flash(f'Status "{name}" created successfully!', 'success')
        
        elif action == 'edit_status':
            status_id = request.form.get('status_id')
            status = Status.query.get(status_id)
            if status:
                status.name = request.form.get('name')
                status.role_type = request.form.get('role_type')
                status.is_final_status = request.form.get('is_final') == 'on'
                status.is_closed_status = request.form.get('is_closed') == 'on'
                status.color = request.form.get('color', 'gray')
                status.description = request.form.get('description')
                db.session.commit()
                flash(f'Status "{status.name}" updated successfully!', 'success')
        
        elif action == 'delete_status':
            status_id = request.form.get('status_id')
            status = Status.query.get(status_id)
            if status and not status.bugs:
                db.session.delete(status)
                db.session.commit()
                flash('Status deleted successfully!', 'success')
            else:
                flash('Cannot delete status with associated bugs.', 'danger')
        
        elif action == 'add_transition':
            from_status_id = request.form.get('from_status_id')
            to_status_id = request.form.get('to_status_id')
            allowed_roles = ','.join(request.form.getlist('allowed_roles'))
            triggers_publish = request.form.get('triggers_publish') == 'on'
            required_for_publish = request.form.get('required_for_publish') == 'on'
            
            existing = StatusTransition.query.filter_by(
                from_status_id=from_status_id,
                to_status_id=to_status_id
            ).first()
            
            if existing:
                existing.allowed_role_types = allowed_roles
                existing.triggers_publish = triggers_publish
                existing.required_for_publish = required_for_publish
                flash('Transition updated successfully!', 'success')
            else:
                transition = StatusTransition(
                    from_status_id=from_status_id,
                    to_status_id=to_status_id,
                    allowed_role_types=allowed_roles,
                    triggers_publish=triggers_publish,
                    required_for_publish=required_for_publish
                )
                db.session.add(transition)
                flash('Transition added successfully!', 'success')
            
            db.session.commit()
        
        elif action == 'delete_transition':
            transition_id = request.form.get('transition_id')
            transition = StatusTransition.query.get(transition_id)
            if transition:
                db.session.delete(transition)
                db.session.commit()
                flash('Transition deleted successfully!', 'success')
        
        return redirect(url_for('main.status_config'))
    
    return render_template('admin/status_config.html',
                          user=user,
                          statuses=statuses,
                          transitions=transitions,
                          role_options=['ALL', 'DEVELOPER', 'TESTER'],
                          color_options=['gray', 'red', 'green', 'blue', 'yellow', 'purple', 'orange'])

@main.route('/view_all_bugs')
@login_required
def view_all_bugs():
    """Displays a simple list of all bugs (potentially for admin/heads)."""
    user = g.user
    all_bugs = Bug.query.all()
    return render_template('view_all_bugs.html', user=user, bugs=all_bugs)

@main.route('/view_bugs/<int:project_id>')
@main.route('/view_bugs/<int:project_id>/<int:bug_id>')
@login_required
def view_bugs(project_id, bug_id=None):
    """Main route for the interactive bug viewer, showing a project's bugs and details for a selected bug."""
    
    user = g.user  # Use g.user for all roles
    user_role_name = 'VIEWER'
    
    if user and user.role:
        user_role_name = user.role.name.upper().replace(' ', '_')
        print(f"DEBUG - view_bugs - user: {user.name}, role: {user.role.name}, role_name: {user_role_name}")

    project = Project.query.get_or_404(project_id)
    
    # Get filter parameters from URL
    filter_release_id = request.args.get('release_id', type=int)
    filter_status = request.args.get('status', type=str)
    
    statuses = Status.query.all()
    priorities = Priority.query.all()
    
    assignable_users = User.query.join(Role).filter(
        Role.name.in_(['Project Head', 'Developer'])
    ).order_by(User.name).all()
    
    reporter_users = User.query.join(Role).filter(
        Role.name.in_(['Tester', 'Testing Head'])
    ).order_by(User.name).all()
    
    selected_bug = Bug.query.get(bug_id) if bug_id else None
    
    # Build query for bugs list with filters
    query = Bug.query.filter(Bug.project_id == project_id)
    
    # Apply release filter if provided
    if filter_release_id:
        query = query.filter(Bug.release_id == filter_release_id)
    
    # Apply status filter if provided
    if filter_status:
        if filter_status.lower() == 'open':
            # Get all statuses that are not closed
            closed_statuses = Status.query.filter(Status.name.in_(['Closed', 'Resolved', 'Verified', 'Done'])).all()
            closed_ids = [s.id for s in closed_statuses]
            query = query.filter(~Bug.status_id.in_(closed_ids))
        elif filter_status.lower() == 'closed':
            closed_statuses = Status.query.filter(Status.name.in_(['Closed', 'Resolved', 'Verified', 'Done'])).all()
            closed_ids = [s.id for s in closed_statuses]
            query = query.filter(Bug.status_id.in_(closed_ids))
        else:
            # Filter by specific status name
            status_obj = Status.query.filter(Status.name.ilike(filter_status)).first()
            if status_obj:
                query = query.filter(Bug.status_id == status_obj.id)
    
    # Get all bugs based on filters
    bugs_in_release = query.order_by(Bug.id.desc()).all()
    
    # If a specific bug is selected, also include it in the list if not already there
    if selected_bug and selected_bug not in bugs_in_release:
        # If we have a release filter and selected bug is from different release, don't add
        if not filter_release_id or selected_bug.release_id == filter_release_id:
            bugs_in_release = [selected_bug] + bugs_in_release

    return render_template('view_bug.html', 
                           current_user=user, 
                           current_user_role_name=user_role_name, 
                           project=project, 
                           selected_bug=selected_bug,
                           statuses=statuses,
                           priorities=priorities,
                           assignable_users=assignable_users,
                           reporter_users=reporter_users,
                           bugs_in_release=bugs_in_release,
                           filter_release_id=filter_release_id,
                           filter_status=filter_status)

@main.route('/api/bugs')
@login_required
def api_bugs():
    """API endpoint for the bug list component (sidebar) with filtering capabilities."""
    
    project_id = request.args.get('project_id', type=int)
    release_id = request.args.get('release_id', type=int)
    search_query = request.args.get('search', '', type=str)
    status_id = request.args.get('status_id', '', type=str)
    
    if not project_id:
        return jsonify([])

    query = Bug.query.filter_by(project_id=project_id)
    
    # Apply release filter if provided
    if release_id:
        query = query.filter_by(release_id=release_id)
    
    if search_query:
        query = query.filter(Bug.title.ilike(f'%{search_query}%'))
    
    if status_id and status_id != 'all':
        try:
            query = query.filter_by(status_id=int(status_id))
        except ValueError:
            pass

    bugs = query.order_by(Bug.id.desc()).all()
    
    bug_data = []
    for bug in bugs:
        bug_data.append({
            'id': bug.id,
            'title': bug.title,
            'status_name': bug.status.name,
            'release_id': bug.release_id
        })
    
    return jsonify(bug_data)

@main.route('/get_bug_details/<int:bug_id>')
@login_required
def get_bug_details(bug_id):
    """API endpoint to fetch detailed information for a single bug with dynamic transitions."""
    user = g.user
    bug = Bug.query.get_or_404(bug_id)
    user_role_type = _get_role_type_for_user(user)

    current_status = bug.status
    allowed_next_statuses = current_status.get_allowed_next_statuses(user_role_type)
    
    statuses_data = []
    for status in allowed_next_statuses:
        statuses_data.append({
            'id': status.id, 
            'name': status.name, 
            'disabled': False
        })
    
    statuses_data.append({
        'id': current_status.id,
        'name': current_status.name,
        'disabled': True
    })
    
    reopen_status = Status.query.filter_by(name='Reopen').first()
    reopen_fields_visible = False
    if reopen_status and user_role_type == 'TESTER':
        reopen_fields_visible = any(s.id == reopen_status.id for s in allowed_next_statuses)

    bug_data = {
        'id': bug.id,
        'title': bug.title,
        'description': bug.description,
        'project_name': bug.project.name,
        'module_name': bug.module.name,
        'sub_module_name': bug.sub_module.name,
        'reporter_name': bug.reporter.name,
        'reporter_id': bug.reporter.id,
        'assigned_to_name': bug.assignee.name,
        'assigned_to_id': bug.assignee.id,
        'priority_name': bug.priority.name,
        'status_name': bug.status.name,
        'status_id': bug.status.id,
        'version_number': bug.release.version_number,
        'reopen_count': bug.reopen_count,
        'timestamp': bug.timestamp.isoformat(),
        'screenshots': [{'file_path': url_for('static', filename='screenshots/' + s.file_path)} for s in bug.screenshots], 
        'history': [{'user_name': h.user.name, 'change_description': h.change_description, 'timestamp': h.timestamp.isoformat()} for h in bug.history],
        'comments': [{'user_name': c.user.name, 'comment_text': c.comment_text, 'timestamp': c.timestamp.isoformat()} for c in bug.comments],
        'is_developer': user_role_type == 'DEVELOPER' or user.role.name == 'Admin',
        'is_tester': user_role_type == 'TESTER',
        'statuses': statuses_data,
        'reopen_fields_visible': reopen_fields_visible
    }
    return jsonify(bug_data)

@main.route('/update_bug_status/<int:bug_id>', methods=['POST'])
@login_required
def update_bug_status(bug_id):
    """Handles updating a single bug's status with dynamic transition rules."""
    user = g.user
    bug = Bug.query.get_or_404(bug_id)
    
    # ========== DEBUG START ==========
    print("\n" + "="*60)
    print("DEBUG - update_bug_status called")
    print("="*60)
    print(f"DEBUG - Bug ID: {bug_id}")
    print(f"DEBUG - User: {user.username}")
    print(f"DEBUG - User Role: {user.role.name if user.role else 'None'}")
    print(f"DEBUG - User Role Name: {user.role.name if user.role else 'None'}")
    
    if bug.release:
        print(f"DEBUG - Release ID: {bug.release.id}")
        print(f"DEBUG - Release Version: {bug.release.version_number}")
        print(f"DEBUG - Release Status: {bug.release.status}")
        print(f"DEBUG - Release testing_started: {bug.release.testing_started}")
    else:
        print(f"DEBUG - Bug has no release associated")
    
    print(f"DEBUG - Bug current status: {bug.status.name}")
    print("="*60)
    # ========== DEBUG END ==========
    
    if user.role.name in ['Developer', 'Project Head']:
        print(f"DEBUG - User is Developer/Project Head, checking release status...")
        if bug.release:
            if bug.release.status != 'in_progress':
                print(f"DEBUG - ❌ BLOCKED: Release status is '{bug.release.status}', expected 'in_progress'")
                status_display = {
                    'active': 'Active (Testing Phase)',
                    'reported': 'Reported (Not yet started)',
                    'submitted_by_tester': 'Submitted (Not yet started)',
                    'ready_for_testing': 'Ready for Testing',
                    'closed': 'Closed'
                }.get(bug.release.status, bug.release.status)
                
                flash(f'❌ Cannot change bug status. Release "{bug.release.version_number}" is not in development state. Current status: {status_display}', 'danger')
                return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))
            else:
                print(f"DEBUG - ✅ ALLOWED: Release status is 'in_progress'")
        else:
            print(f"DEBUG - ✅ ALLOWED: Bug has no release")
    else:
        print(f"DEBUG - User is not Developer/Project Head, skipping release check")
    
    new_status_id = request.form.get('status')
    print(f"DEBUG - New status ID from form: {new_status_id}")
    user_role_type = _get_role_type_for_user(user)
    print(f"DEBUG - User role type: {user_role_type}")
    
    try:
        new_status = Status.query.get_or_404(new_status_id)
        print(f"DEBUG - New status name: {new_status.name}")
    except:
        print(f"DEBUG - ❌ Invalid status ID: {new_status_id}")
        flash("Invalid status selected.", 'danger')
        return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))
        
    old_status_name = bug.status.name
    new_status_name = new_status.name
    
    # Check if transition is allowed
    allowed_transition = StatusTransition.query.filter_by(
        from_status_id=bug.status_id,
        to_status_id=new_status_id
    ).first()
    
    print(f"DEBUG - Allowed transition exists: {allowed_transition is not None}")
    
    if not allowed_transition:
        print(f"DEBUG - ❌ Transition not allowed: {old_status_name} -> {new_status_name}")
        flash(f"Transition from '{bug.status.name}' to '{new_status_name}' is not allowed in the system.", 'danger')
        return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))
    
    allowed_roles = allowed_transition.allowed_role_types.split(',')
    print(f"DEBUG - Allowed roles for transition: {allowed_roles}")
    
    if user_role_type not in allowed_roles and 'ALL' not in allowed_roles:
        print(f"DEBUG - ❌ User role type '{user_role_type}' not allowed for this transition")
        flash(f"Your role ({user.role.name}) is not allowed to change bug from '{bug.status.name}' to '{new_status_name}'.", 'danger')
        return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))
    
    print(f"DEBUG - ✅ User role allowed for transition")

    if bug.status_id != new_status.id:
        print(f"DEBUG - Updating status from {old_status_name} to {new_status_name}")
        
        if new_status_name == 'Reopen':
            print(f"DEBUG - Handling Reopen operation")
            bug.reopen_count += 1
            reopen_comment = request.form.get('reopen_comment')
            
            if reopen_comment:
                print(f"DEBUG - Adding reopen comment: {reopen_comment[:50]}...")
                comment = Comment(comment_text=f"(Reopen Comment) {reopen_comment}", bug_id=bug.id, user_id=user.id)
                db.session.add(comment)
            
            if 'new_screenshot' in request.files:
                file = request.files['new_screenshot']
                if file and file.filename != '':
                    try:
                        print(f"DEBUG - Saving reopen screenshot: {file.filename}")
                        timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                        filename = secure_filename(f'reopen_{bug.id}_{bug.reopen_count}_{timestamp_str}_{file.filename}')
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        file.save(file_path)
                        
                        screenshot = BugScreenshot(bug_id=bug.id, file_path=filename)
                        db.session.add(screenshot)
                        print(f"DEBUG - Screenshot saved: {filename}")
                    except Exception as e:
                        print(f"!!! CRITICAL FILE ERROR during Reopen screenshot save for Bug {bug.id}: {e}")
                        traceback.print_exc()

        bug.status_id = new_status.id
        db.session.commit()
        
        change_description = f"Status changed from '{old_status_name}' to '{new_status_name}'."
        history_record = BugHistory(bug=bug, user_id=user.id, change_description=change_description)
        db.session.add(history_record)
        db.session.commit()
        
        print(f"DEBUG - ✅ Status update successful!")
        flash('Bug status updated successfully!', 'success')
    else:
        print(f"DEBUG - Status already {old_status_name}, no change needed")
        flash('Bug status is already the selected status.', 'info')
    
    print("="*60 + "\n")
    return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))
@main.route('/add_comment/<int:bug_id>', methods=['POST'])
@login_required
def add_comment(bug_id):
    """Adds a new comment to a bug."""
    user = g.user
    bug = Bug.query.get_or_404(bug_id)
    content = request.form.get('content')

    if content:
        new_comment = Comment(comment_text=content, bug_id=bug.id, user_id=user.id)
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')
    
    return redirect(url_for('main.view_bugs', project_id=bug.project_id, bug_id=bug.id))

@main.route('/bulk_update_bugs', methods=['POST'])
@login_required
@permission_required(allowed_roles=['Developer', 'Project Head'])
def bulk_update_bugs():
    """Handles bulk status updates for multiple bugs, using dynamic transition rules."""
    user = g.user
    status_id = request.form.get('status_id')
    bug_ids_str = request.form.get('bug_ids')
    user_role_type = _get_role_type_for_user(user)
    
    if not status_id or not bug_ids_str:
        flash('Status and bug IDs are required.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        bug_ids = [int(x.strip()) for x in bug_ids_str.split(',')]
    except (ValueError, IndexError):
        flash('Invalid bug ID list format.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    bugs_to_update = Bug.query.filter(Bug.id.in_(bug_ids)).all()
    new_status = Status.query.get(status_id)
    
    if not new_status:
        flash('Invalid status selected.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    invalid_release_status = False
    release_status_issues = {}
    
    for bug in bugs_to_update:
        if bug.release:
            if bug.release.status != 'in_progress':
                invalid_release_status = True
                release_status_issues[bug.release.version_number] = bug.release.status
    
    if invalid_release_status:
        issue_details = []
        for version, status in release_status_issues.items():
            status_display = {
                'active': 'Active (Testing Phase)',
                'reported': 'Reported (Not started)',
                'submitted_by_tester': 'Submitted (Not started)',
                'ready_for_testing': 'Ready for Testing',
                'closed': 'Closed'
            }.get(status, status)
            issue_details.append(f"{version} ({status_display})")
        
        flash(f'❌ Cannot update bugs. Releases not in development state: {", ".join(issue_details)}', 'danger')
        return redirect(url_for('main.dashboard'))
    
    updated_count = 0
    for bug in bugs_to_update:
        allowed_transition = StatusTransition.query.filter_by(
            from_status_id=bug.status_id,
            to_status_id=status_id
        ).first()
        
        if not allowed_transition:
            continue
        
        allowed_roles = allowed_transition.allowed_role_types.split(',')
        if user_role_type not in allowed_roles and 'ALL' not in allowed_roles:
            continue

        if bug.status_id != new_status.id:
            old_status_name = bug.status.name
            bug.status_id = new_status.id
            change_description = f"Status changed from '{old_status_name}' to '{new_status.name}' via bulk update."
            history_record = BugHistory(bug=bug, user_id=user.id, change_description=change_description)
            db.session.add(history_record)
            updated_count += 1

    db.session.commit()
    
    if updated_count > 0:
        flash(f'{updated_count} bugs updated successfully!', 'success')
    else:
        flash('No bugs were updated. Check if transitions are allowed.', 'warning')
    
    return redirect(url_for('main.dashboard'))
