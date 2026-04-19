from flask import Blueprint, render_template, session
from auth import get_db, student_required

# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------

student_bp = Blueprint('student', __name__, url_prefix='/student')

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@student_bp.route('/dashboard')
@student_required
def dashboard():
    """
    Central hub for the student:
    - All uploaded artworks with thumbnails, grade badge, and upload date
    - Portfolios summary
    - Count of unread / new teacher comments
    """
    db = get_db()
    student_id = session['user_id']

    # All artworks ordered by upload date descending
    artworks = db.execute(
        """
        SELECT a.*,
               (SELECT MAX(c.created_at)
                FROM comments c
                WHERE c.artwork_id = a.artwork_id) AS latest_feedback_date
        FROM artworks a
        WHERE a.student_id = ?
        ORDER BY a.upload_date DESC
        """,
        (student_id,)
    ).fetchall()

    # Portfolios for sidebar / summary
    portfolios = db.execute(
        """
        SELECT p.*, COUNT(pa.artwork_id) AS artwork_count
        FROM portfolios p
        LEFT JOIN portfolio_artworks pa ON pa.portfolio_id = p.portfolio_id
        WHERE p.student_id = ?
        GROUP BY p.portfolio_id
        ORDER BY p.updated_date DESC
        """,
        (student_id,)
    ).fetchall()

    # Count of artworks that have new teacher comments (unread feedback)
    # We treat any comment created after the artwork's last_viewed_at as "new".
    # For simplicity here we count artworks with at least one comment.
    new_feedback_count = db.execute(
        """
        SELECT COUNT(DISTINCT c.artwork_id)
        FROM comments c
        JOIN artworks a ON a.artwork_id = c.artwork_id
        WHERE a.student_id = ?
        """,
        (student_id,)
    ).fetchone()[0]

    return render_template(
        'student/dashboard.html',
        artworks=artworks,
        portfolios=portfolios,
        new_feedback_count=new_feedback_count
    )