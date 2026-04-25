from flask import Blueprint, render_template
from auth import get_db, teacher_required
 
# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------
 
teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')
 
# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
 
@teacher_bp.route('/dashboard')
@teacher_required
def dashboard():
    """
    Teacher dashboard - shows overview of student work.
    """
    # TODO: Add grading functionality
    return render_template('teacher/dashboard.html')
 
