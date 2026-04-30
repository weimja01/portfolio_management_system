from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, jsonify
)

from auth import get_db, teacher_required, log_action

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
    Teacher dashboard - shows all submitted artwork and review status.
    """
    db = get_db()

    status = request.args.get('status', 'all')
    search = request.args.get('search', '').strip()

    query = """
        SELECT a.*, u.first_name, u.last_name,
               CASE
                   WHEN a.grade IS NOT NULL THEN 'graded'
                   WHEN EXISTS (
                       SELECT 1 FROM comments c
                       WHERE c.artwork_id = a.artwork_id
                   ) THEN 'commented'
                   ELSE 'ungraded'
               END AS review_status
        FROM artworks a
        JOIN users u ON u.user_id = a.student_id
        WHERE 1 = 1
    """

    params = []

    if search:
        query += """
            AND (
                a.title LIKE ?
                OR a.medium LIKE ?
                OR u.first_name LIKE ?
                OR u.last_name LIKE ?
            )
        """
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search, like_search])

    query += " ORDER BY a.upload_date DESC"

    submissions = db.execute(query, params).fetchall()

    if status in ('ungraded', 'commented', 'graded'):
        submissions = [
            row for row in submissions
            if row['review_status'] == status
        ]

    stats = {
        'total': len(submissions),
        'ungraded': sum(1 for row in submissions if row['review_status'] == 'ungraded'),
        'commented': sum(1 for row in submissions if row['review_status'] == 'commented'),
        'graded': sum(1 for row in submissions if row['review_status'] == 'graded')
    }

    return render_template(
        'teacher/dashboard.html',
        submissions=submissions,
        stats=stats,
        status=status,
        search=search
    )

@teacher_bp.route('/grade/<int:artwork_id>', methods=['POST'])
@teacher_required
def grade_artwork(artwork_id):
    """Grade artwork via HTML form submission."""
    grade = request.form.get('grade')
    
    if not grade or not grade.isdigit():
        flash("Invalid grade. Please enter a number between 0 and 100.", "danger")
        return redirect(url_for('artworks.detail', artwork_id=artwork_id))
    
    grade = int(grade)
    if grade < 0 or grade > 100:
        flash("Grade must be between 0 and 100.", "danger")
        return redirect(url_for('artworks.detail', artwork_id=artwork_id))
    
    db = get_db()
    db.execute(
        "UPDATE artworks SET grade = ? WHERE artwork_id = ?",
        (grade, artwork_id)
    )
    db.commit()
    
    flash(f"Grade of {grade}% saved successfully!", "success")
    return redirect(url_for('artworks.detail', artwork_id=artwork_id))

@teacher_bp.route('/review/<int:artwork_id>', methods=['GET', 'POST'])
@teacher_required
def review(artwork_id):
    """
    Allow a teacher to review, comment on, and grade a student's artwork.
    """
    db = get_db()

    artwork = db.execute(
        """
        SELECT a.*, u.first_name, u.last_name, u.email
        FROM artworks a
        JOIN users u ON u.user_id = a.student_id
        WHERE a.artwork_id = ?
        """,
        (artwork_id,)
    ).fetchone()

    if artwork is None:
        flash("Artwork not found.", "warning")
        return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        grade_text = request.form.get('grade', '').strip()
        comment_text = request.form.get('comment_text', '').strip()

        grade = None

        if grade_text:
            try:
                grade = float(grade_text)
            except ValueError:
                flash("Grade must be a number from 0 to 100.", "danger")
                return redirect(url_for('teacher.review', artwork_id=artwork_id))

            if grade < 0 or grade > 100:
                flash("Grade must be between 0 and 100.", "danger")
                return redirect(url_for('teacher.review', artwork_id=artwork_id))

        if grade is None and not comment_text:
            flash("Please enter a grade, a comment, or both.", "danger")
            return redirect(url_for('teacher.review', artwork_id=artwork_id))

        if grade is not None:
            db.execute(
                """
                UPDATE artworks
                SET grade = ?
                WHERE artwork_id = ?
                """,
                (grade, artwork_id)
            )

        if comment_text:
            db.execute(
                """
                INSERT INTO comments
                    (artwork_id, teacher_id, comment_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    artwork_id,
                    session['user_id'],
                    comment_text,
                    datetime.utcnow().isoformat()
                )
            )

        db.commit()

        log_action(
            session['user_id'],
            "teacher_feedback",
            f"Teacher reviewed artwork ID {artwork_id}"
        )

        flash("Feedback saved successfully.", "success")

        if request.form.get('save_next') == '1':
            next_artwork = db.execute(
                """
                SELECT artwork_id
                FROM artworks
                WHERE grade IS NULL
                  AND artwork_id != ?
                ORDER BY upload_date ASC
                LIMIT 1
                """,
                (artwork_id,)
            ).fetchone()

            if next_artwork:
                return redirect(
                    url_for('teacher.review', artwork_id=next_artwork['artwork_id'])
                )

        return redirect(url_for('teacher.dashboard'))

    comments = db.execute(
        """
        SELECT c.*, u.first_name || ' ' || u.last_name AS teacher_name
        FROM comments c
        JOIN users u ON u.user_id = c.teacher_id
        WHERE c.artwork_id = ?
        ORDER BY c.created_at DESC
        """,
        (artwork_id,)
    ).fetchall()

    return render_template(
        'teacher/review.html',
        artwork=artwork,
        comments=comments
    )


@teacher_bp.route('/api/artworks/<int:artwork_id>/grade', methods=['POST', 'PUT'])
@teacher_required
def api_grade(artwork_id):
    """
    API endpoint for grading artwork.
    """
    data = request.get_json(silent=True) or request.form

    grade_text = data.get('grade')
    comment_text = data.get('comment_text', '').strip()

    try:
        grade = float(grade_text)
    except (TypeError, ValueError):
        return jsonify({
            "status": "error",
            "message": "Grade must be numeric."
        }), 400

    if grade < 0 or grade > 100:
        return jsonify({
            "status": "error",
            "message": "Grade must be between 0 and 100."
        }), 400

    db = get_db()

    artwork = db.execute(
        "SELECT artwork_id FROM artworks WHERE artwork_id = ?",
        (artwork_id,)
    ).fetchone()

    if artwork is None:
        return jsonify({
            "status": "error",
            "message": "Artwork not found."
        }), 404

    db.execute(
        "UPDATE artworks SET grade = ? WHERE artwork_id = ?",
        (grade, artwork_id)
    )

    if comment_text:
        db.execute(
            """
            INSERT INTO comments
                (artwork_id, teacher_id, comment_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                artwork_id,
                session['user_id'],
                comment_text,
                datetime.utcnow().isoformat()
            )
        )

    db.commit()

    return jsonify({
        "status": "success",
        "message": "Grade saved successfully."
    }), 200