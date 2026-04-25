import sqlite3
import re
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, request, session, redirect,
    url_for, render_template, flash, g, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

DATABASE = 'portfolio.db'


def get_db():
    """Return a database connection, reusing one already open on `g`."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row       # enables dict-like column access
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    """Close the database connection at the end of each request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Audit logging helper
# ---------------------------------------------------------------------------

def log_action(user_id, action_type, details=None):
    """Write an entry to the audit_log table."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO audit_log (user_id, action_type, action_date, details)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, action_type, datetime.utcnow().isoformat(), details)
        )
        db.commit()
    except Exception:
        # Audit logging must never crash the main request
        pass


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
MIN_PASSWORD_LENGTH = 8


def validate_registration_input(form):
    """
    Validate all registration form fields.
    Returns a list of error strings; empty list means input is valid.
    """
    errors = []

    # Required field checks
    required = ['first_name', 'last_name', 'username', 'email', 'password', 'confirm_password', 'role']
    for field in required:
        if not form.get(field, '').strip():
            errors.append(f"{field.replace('_', ' ').title()} is required.")

    if errors:
        return errors  # Stop early if required fields are missing

    # Email format check
    if not EMAIL_REGEX.match(form['email'].strip()):
        errors.append("Please enter a valid email address.")

    # Password length
    if len(form['password']) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")

    # Password confirmation
    if form['password'] != form['confirm_password']:
        errors.append("Passwords do not match.")

    # Role validation
    if form['role'] not in ('student', 'teacher'):
        errors.append("Role must be either 'student' or 'teacher'.")

    # Optional grad_year: if provided, must be a valid integer
    grad_year = form.get('grad_year', '').strip()
    if grad_year:
        try:
            year = int(grad_year)
            if year < 2000 or year > 2100:
                errors.append("Graduation year must be between 2000 and 2100.")
        except ValueError:
            errors.append("Graduation year must be a valid number.")

    return errors


# ---------------------------------------------------------------------------
# Role-based access decorators
# ---------------------------------------------------------------------------

def login_required(f):
    """Redirect to login page if the user is not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    """Allow access only to users with the 'student' role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        if session.get('role') != 'student':
            flash("Access denied. Student accounts only.", "danger")
            return redirect(url_for('auth.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """Allow access only to users with the 'teacher' role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        if session.get('role') != 'teacher':
            flash("Access denied. Teacher accounts only.", "danger")
            return redirect(url_for('auth.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Allow access only to users with the 'admin' role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash("Access denied. Administrator accounts only.", "danger")
            return redirect(url_for('auth.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Authentication routes
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handle new user registration.

    GET  – Display the registration form.
    POST – Validate input, check for duplicate email/username, hash the
           password, insert the new user record, and redirect to login.
    """
    if 'user_id' in session:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        form = request.form

        # --- Validate input ---
        errors = validate_registration_input(form)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template('auth/register.html', form=form), 400

        first_name    = form['first_name'].strip()
        last_name     = form['last_name'].strip()
        username      = form['username'].strip()
        email         = form['email'].strip().lower()
        password      = form['password']
        role          = form['role']
        grad_year     = int(form['grad_year']) if form.get('grad_year', '').strip() else None
        department    = form.get('department', '').strip() or None

        db = get_db()

        # --- Check for duplicate email ---
        existing_email = db.execute(
            "SELECT user_id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing_email:
            flash("An account with that email address already exists.", "danger")
            return render_template('auth/register.html', form=form), 409

        # --- Check for duplicate username ---
        existing_username = db.execute(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing_username:
            flash("That username is already taken. Please choose another.", "danger")
            return render_template('auth/register.html', form=form), 409

        # --- Hash the password (bcrypt via Werkzeug) ---
        password_hash = generate_password_hash(password)

        # --- Insert new user record ---
        try:
            cursor = db.execute(
                """
                INSERT INTO users
                    (username, email, password_hash, role,
                     first_name, last_name, grad_year, department, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username, email, password_hash, role,
                    first_name, last_name, grad_year, department,
                    datetime.utcnow().isoformat()
                )
            )
            db.commit()
            new_user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            # Catch any remaining UNIQUE constraint violations
            flash("Registration failed due to a conflict. Please try again.", "danger")
            return render_template('auth/register.html', form=form), 409

        # --- Audit log ---
        log_action(new_user_id, "register", f"New {role} account created for {email}")

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('auth.login'))

    # GET request: render blank form
    return render_template('auth/register.html', form={})


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle user login.

    GET  – Display the login form.
    POST – Look up the user by email, verify the password hash, open a
           session, and redirect to the role-appropriate dashboard.
    """
    if 'user_id' in session:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Basic presence check
        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template('auth/login.html'), 400

        db = get_db()
        user = db.execute(
            """
            SELECT user_id, username, email, password_hash,
                   role, first_name, last_name, account_status
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        # --- Verify password ---
        if user is None or not check_password_hash(user['password_hash'], password):
            # Log failed attempt (no user_id available if user not found)
            if user:
                log_action(user['user_id'], "login_failed", f"Bad password for {email}")
            flash("Invalid email or password.", "danger")
            return render_template('auth/login.html'), 401

        # --- Check account status ---
        if user['account_status'] == 'inactive':
            flash("Your account is inactive. Please contact an administrator.", "warning")
            return render_template('auth/login.html'), 403

        if user['account_status'] == 'suspended':
            flash("Your account has been suspended. Please contact an administrator.", "danger")
            return render_template('auth/login.html'), 403

        # --- Open session ---
        session.clear()
        session['user_id']    = user['user_id']
        session['username']   = user['username']
        session['role']       = user['role']
        session['first_name'] = user['first_name']
        session['last_name']  = user['last_name']
        session.permanent     = True    # respect Flask's PERMANENT_SESSION_LIFETIME

        # --- Audit log ---
        log_action(user['user_id'], "login_success", f"Login from {request.remote_addr}")

        flash(f"Welcome back, {user['first_name']}!", "success")
        return redirect(url_for('auth.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required  
def logout():
    """Securely log the user out."""
    user_id = session.get('user_id')
    
    log_action(user_id, "logout", "User logged out")
    
    # Clear ALL session data
    session.clear()
    session.modified = False
    session.permanent = False
    
    # Create response
    response = make_response(redirect(url_for('auth.login')))
    
    # Delete session cookie completely
    response.delete_cookie('session', path='/')
    
    return response


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Route users to their role-appropriate dashboard after login.
    Acts as a central dispatcher so every login redirect lands here.
    """
    role = session.get('role')

    if role == 'student':
        return redirect(url_for('student.dashboard'))
    elif role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin.dashboard'))

    # Fallback: unexpected role — force logout
    session.clear()
    flash("Unknown account role. Please contact an administrator.", "danger")
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# API endpoints (JSON) — matches Design Document API table
# ---------------------------------------------------------------------------

from flask import jsonify


@auth_bp.route('/api/auth/login', methods=['POST'])
def api_login():
    """
    POST /api/auth/login
    JSON body: { "email": "...", "password": "..." }
    Returns a session cookie on success.
    """
    if not request.is_json:
        return jsonify({"status": "error", "message": "Content-Type must be application/json"}), 415

    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password are required."}), 400

    db = get_db()
    user = db.execute(
        """
        SELECT user_id, username, email, password_hash,
               role, first_name, last_name, account_status
        FROM users WHERE email = ?
        """,
        (email,)
    ).fetchone()

    if user is None or not check_password_hash(user['password_hash'], password):
        if user:
            log_action(user['user_id'], "api_login_failed", f"Bad password for {email}")
        return jsonify({"status": "error", "message": "Invalid email or password."}), 401

    if user['account_status'] in ('inactive', 'suspended'):
        return jsonify({"status": "error", "message": f"Account is {user['account_status']}."}), 403

    session.clear()
    session['user_id']    = user['user_id']
    session['username']   = user['username']
    session['role']       = user['role']
    session['first_name'] = user['first_name']
    session['last_name']  = user['last_name']

    log_action(user['user_id'], "api_login_success", f"API login from {request.remote_addr}")

    return jsonify({
        "status":  "success",
        "message": "Login successful.",
        "data": {
            "user_id":    user['user_id'],
            "username":   user['username'],
            "role":       user['role'],
            "first_name": user['first_name'],
            "last_name":  user['last_name']
        }
    }), 200


@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    """
    POST /api/auth/logout
    Requires an active session cookie (session token).
    """
    user_id = session.get('user_id')
    log_action(user_id, "api_logout", "User logged out via API")
    session.clear()
    return jsonify({"status": "success", "message": "Logged out successfully."}), 200


# ---------------------------------------------------------------------------
# App factory integration helpers
# ---------------------------------------------------------------------------

def init_app(app):
    """
    Register the authentication blueprint and teardown handler with a
    Flask application instance.

    Usage in app.py:
        from auth import init_app as init_auth
        init_auth(app)
    """
    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)