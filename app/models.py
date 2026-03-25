from app import db, bcrypt
from datetime import datetime
from sqlalchemy.orm import relationship

# Helper table for many-to-many relationship between users and projects
user_project_assignment = db.Table('user_project_assignment',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('project_id', db.Integer, db.ForeignKey('project.id'))
)

# New helper table for many-to-many relationship between releases and testers
release_testers = db.Table('release_testers',
    db.Column('release_id', db.Integer, db.ForeignKey('release.id')),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'))
)

class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    # This is the corrected column that was missing
    hierarchy_level = db.Column(db.Integer, nullable=True) 
    description = db.Column(db.String(200))
    users = relationship('User', back_populates='role')

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    
    role = relationship('Role', back_populates='users')
    
    assigned_bugs = relationship('Bug', back_populates='assignee', foreign_keys='Bug.assigned_to_id')
    reported_bugs = relationship('Bug', back_populates='reporter', foreign_keys='Bug.reporter_id')
    
    projects = relationship(
        'Project', 
        secondary=user_project_assignment, 
        back_populates='users'
    )
    
    assigned_releases = relationship(
        'Release',
        secondary=release_testers,
        back_populates='assigned_users'
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    bugs = relationship('Bug', back_populates='project', cascade='all, delete-orphan')
    modules = relationship('Module', back_populates='project', cascade='all, delete-orphan')
    releases = relationship('Release', back_populates='project', cascade='all, delete-orphan')
    
    users = relationship(
        'User', 
        secondary=user_project_assignment, 
        back_populates='projects'
    )

class Module(db.Model):
    __tablename__ = 'module'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    
    project = relationship('Project', back_populates='modules')
    sub_modules = relationship('SubModule', back_populates='module', cascade='all, delete-orphan')
    bugs = relationship('Bug', back_populates='module', cascade='all, delete-orphan')

class SubModule(db.Model):
    __tablename__ = 'sub_module'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'), nullable=False)
    
    module = relationship('Module', back_populates='sub_modules')
    bugs = relationship('Bug', back_populates='sub_module', cascade='all, delete-orphan')

class Release(db.Model):
    __tablename__ = 'release'
    id = db.Column(db.Integer, primary_key=True)
    version_number = db.Column(db.String(50), nullable=False)
    released_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    release_note = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    # NEW: Mark if release is active for bug reporting
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # NEW FIELDS for release lifecycle
    status = db.Column(db.String(20), default='active', nullable=False)  
    # Possible values: 
    # 'active' - Testers can add bugs
    # 'submitted_by_tester' - Testing head submitted, developers can fix
    # 'in_progress' - Developers are fixing bugs
    # 'ready_for_testing' - Developers done, ready for testers to verify
    # 'closed' - Release cycle complete
    # 'reported' - Testing Head has reported the build
    
    # NEW: Track if testing has started for this release
    testing_started = db.Column(db.Boolean, default=False, nullable=False)
    
    parent_release_id = db.Column(db.Integer, db.ForeignKey('release.id'), nullable=True)
    submitted_by_tester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    submitted_by_developer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    project = relationship('Project', back_populates='releases')
    bugs = relationship('Bug', back_populates='release', cascade='all, delete-orphan')
    released_by = relationship('User', foreign_keys=[released_by_id], backref='releases_created')
    
    # New relationship for submission users
    submitted_by_tester = relationship('User', foreign_keys=[submitted_by_tester_id], backref='releases_submitted_as_tester')
    submitted_by_developer = relationship('User', foreign_keys=[submitted_by_developer_id], backref='releases_submitted_as_developer')
    
    # Self-referential relationship for release hierarchy
    parent_release = relationship('Release', remote_side=[id], backref='child_releases')
    
    assigned_users = relationship(
        'User',
        secondary=release_testers,
        back_populates='assigned_releases'
    )
    
    def get_all_bugs_count(self):
        """Get total number of bugs in this release"""
        return len(self.bugs)
    
    def get_open_bugs_count(self):
        """Get number of open bugs in this release"""
        return sum(1 for bug in self.bugs if bug.status.name not in ['Closed', 'Verified', 'Done', 'Resolved'])
    
    def get_closed_bugs_count(self):
        """Get number of closed bugs in this release"""
        return sum(1 for bug in self.bugs if bug.status.name in ['Closed', 'Verified', 'Done', 'Resolved'])
    
    def get_bugs_by_status(self, status_name):
        """Get bugs filtered by status name"""
        return [bug for bug in self.bugs if bug.status.name == status_name]
    
    def can_testers_add_bugs(self):
        """Testers can only add bugs when release is active and testing has started"""
        return self.is_active and self.status == 'active' and self.testing_started
    
    def can_testers_verify(self):
        """Testers can verify bugs when release is ready for testing"""
        return self.status == 'ready_for_testing'
    
    def can_developers_edit(self):
        """Developers can edit when release is in progress"""
        return self.status in ['submitted_by_tester', 'in_progress']
    
    def can_testing_head_submit(self):
        """Testing head can submit when testing has started and there are bugs"""
        return self.status == 'active' and self.is_active and self.testing_started and self.get_all_bugs_count() > 0
    
    def can_developer_submit(self):
        """Developer can submit when they've finished fixing bugs"""
        return self.status == 'in_progress'
    
    def can_start_testing(self):
        """Check if testing can be started on this release"""
        return self.status == 'active' and not self.testing_started
    
    def is_fully_tested(self):
        """Check if all bugs are either closed or verified"""
        non_closed = [b for b in self.bugs if b.status.name not in ['Closed', 'Verified', 'Done', 'Resolved']]
        return len(non_closed) == 0
    
    def get_testing_progress(self):
        """Get progress percentage for testing"""
        if not self.bugs:
            return 0
        closed = self.get_closed_bugs_count()
        return int((closed / len(self.bugs)) * 100)
    
    # ========== NEW PUBLISH LOGIC METHODS ==========
    
    def can_publish(self):
        """
        Check if this release can be published based on admin configuration.
        Returns True if at least one bug has reached a status that triggers publish.
        """
        if self.status != 'in_progress':
            return False
        
        # Import here to avoid circular imports
        from app.models import StatusTransition
        
        # Check if any bug has reached a status that triggers publish
        for bug in self.bugs:
            transitions = StatusTransition.query.filter_by(
                to_status_id=bug.status_id,
                triggers_publish=True
            ).all()
            
            if transitions:
                return True
        
        return False
    
    def get_publish_ready_count(self):
        """
        Get number of bugs that are in publish-triggering statuses.
        """
        from app.models import StatusTransition
        
        count = 0
        for bug in self.bugs:
            transitions = StatusTransition.query.filter_by(
                to_status_id=bug.status_id,
                triggers_publish=True
            ).all()
            if transitions:
                count += 1
        return count
    
    def get_publish_ready_bugs(self):
        """
        Get list of bugs that are ready to trigger publish.
        """
        from app.models import StatusTransition
        
        ready_bugs = []
        for bug in self.bugs:
            transitions = StatusTransition.query.filter_by(
                to_status_id=bug.status_id,
                triggers_publish=True
            ).all()
            if transitions:
                ready_bugs.append(bug)
        return ready_bugs
    
    def get_publish_progress(self):
        """
        Get progress percentage based on publish-ready bugs.
        """
        if not self.bugs:
            return 0
        ready = self.get_publish_ready_count()
        return int((ready / len(self.bugs)) * 100)
    
    def get_non_publish_ready_bugs(self):
        """
        Get bugs that are not yet in publish-triggering statuses.
        """
        from app.models import StatusTransition
        
        non_ready = []
        for bug in self.bugs:
            transitions = StatusTransition.query.filter_by(
                to_status_id=bug.status_id,
                triggers_publish=True
            ).all()
            if not transitions:
                non_ready.append(bug)
        return non_ready
    
    def get_publish_ready_statuses(self):
        """
        Get all statuses that are configured to trigger publish.
        """
        from app.models import StatusTransition, Status
        
        status_ids = db.session.query(StatusTransition.to_status_id).filter(
            StatusTransition.triggers_publish == True
        ).distinct().all()
        status_ids = [s[0] for s in status_ids]
        
        return Status.query.filter(Status.id.in_(status_ids)).all()
    
    def create_child_release(self, new_version_number, released_by):
        """Create a new release based on this one with all bugs copied"""
        child = Release(
            version_number=new_version_number,
            released_by_id=released_by,
            release_note=f"Auto-created from release {self.version_number}",
            project_id=self.project_id,
            is_active=True,
            status='active',
            parent_release_id=self.id,
            testing_started=False
        )
        return child
    
    def __repr__(self):
        return f'<Release {self.version_number} ({self.status})>'
    
            
# The combined and corrected Bug model
class Bug(db.Model):
    __tablename__ = 'bug'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    reopen_count = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    
    # Foreign keys
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'), nullable=False)
    sub_module_id = db.Column(db.Integer, db.ForeignKey('sub_module.id'), nullable=False)
    priority_id = db.Column(db.Integer, db.ForeignKey('priority.id'), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=False)
    
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'), nullable=False)

    # Relationships
    project = relationship('Project', back_populates='bugs')
    module = relationship('Module', back_populates='bugs')
    sub_module = relationship('SubModule', back_populates='bugs')
    priority = relationship('Priority', back_populates='bugs')
    status = relationship('Status', back_populates='bugs')
    release = relationship('Release', back_populates='bugs')

    reporter = relationship('User', back_populates='reported_bugs', foreign_keys=[reporter_id])
    assignee = relationship('User', back_populates='assigned_bugs', foreign_keys=[assigned_to_id])

    history = relationship('BugHistory', back_populates='bug', cascade='all, delete-orphan')
    screenshots = relationship('BugScreenshot', back_populates='bug', cascade='all, delete-orphan')
    comments = relationship('Comment', back_populates='bug', cascade='all, delete-orphan')

class Priority(db.Model):
    __tablename__ = 'priority'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    bugs = relationship('Bug', back_populates='priority', cascade='all, delete-orphan')


class Status(db.Model):
    __tablename__ = 'status'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    role_type = db.Column(db.String(20), default='ALL', nullable=False)
    # NEW FIELDS
    is_final_status = db.Column(db.Boolean, default=False)  # Is this a "bug fixed" status?
    is_closed_status = db.Column(db.Boolean, default=False)  # Is this a closed/completed status?
    color = db.Column(db.String(20), default='gray')  # Status color in UI
    description = db.Column(db.String(200))
    
    bugs = relationship('Bug', back_populates='status', cascade='all, delete-orphan')
    
    transitions_from = relationship('StatusTransition', 
                                    foreign_keys='StatusTransition.from_status_id',
                                    back_populates='from_status', 
                                    cascade='all, delete-orphan')
    transitions_to = relationship('StatusTransition', 
                                  foreign_keys='StatusTransition.to_status_id',
                                  back_populates='to_status', 
                                  cascade='all, delete-orphan')
    
    def get_allowed_next_statuses(self, user_role_type):
        """Returns list of status objects that this status can transition to"""
        allowed_statuses = []
        for transition in self.transitions_from:
            allowed_roles = transition.allowed_role_types.split(',')
            if user_role_type in allowed_roles or 'ALL' in allowed_roles:
                allowed_statuses.append(transition.to_status)
        return allowed_statuses
    
    def __repr__(self):
        return f'<Status {self.name}>'


class StatusTransition(db.Model):
    __tablename__ = 'status_transition'
    id = db.Column(db.Integer, primary_key=True)
    from_status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=False)
    to_status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=False)
    allowed_role_types = db.Column(db.String(100), nullable=False, default='ALL')
    
    # NEW FIELDS
    triggers_publish = db.Column(db.Boolean, default=False)  # Does this transition trigger publish?
    required_for_publish = db.Column(db.Boolean, default=False)  # Must all bugs reach this?
    
    from_status = db.relationship('Status', foreign_keys=[from_status_id], back_populates='transitions_from')
    to_status = db.relationship('Status', foreign_keys=[to_status_id], back_populates='transitions_to')
    
    __table_args__ = (db.UniqueConstraint('from_status_id', 'to_status_id', name='unique_transition'),)
    
    def __repr__(self):
        return f'<StatusTransition {self.from_status.name} -> {self.to_status.name}>'


class BugHistory(db.Model):
    __tablename__ = 'bug_history'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey('bug.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    change_description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    
    bug = relationship('Bug', back_populates='history')
    user = relationship('User', backref='bug_history', lazy=True)

class BugScreenshot(db.Model):
    __tablename__ = 'bug_screenshot'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey('bug.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    
    bug = relationship('Bug', back_populates='screenshots')

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey('bug.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    
    bug = relationship('Bug', back_populates='comments')
    user = relationship('User', backref='comments', lazy=True)