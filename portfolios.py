import json
from datetime import datetime

from flask import (
    Blueprint, request, session, redirect,
    url_for, render_template, flash, jsonify
)

from auth import get_db, login_required, student_required, teacher_required, log_action

# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------

portfolios_bp = Blueprint('portfolios', __name__, url_prefix='/portfolios')

# ---------------------------------------------------------------------------
# Routes — Student Portfolio Management
# ---------------------------------------------------------------------------

@portfolios_bp.route('/')
@student_required
def index():
    """List all portfolios belonging to the logged-in student."""
    db = get_db()
    portfolios = db.execute(
        """
        SELECT p.*,
               COUNT(a.artwork_id) AS artwork_count
        FROM portfolios p
        LEFT JOIN portfolio_artworks pa ON pa.portfolio_id = p.portfolio_id
        LEFT JOIN artworks a            ON a.artwork_id    = pa.artwork_id
        WHERE p.student_id = ?
        GROUP BY p.portfolio_id
        ORDER BY p.created_date DESC
        """,
        (session['user_id'],)
    ).fetchall()

    return render_template('portfolios/index.html', portfolios=portfolios)


@portfolios_bp.route('/create', methods=['GET', 'POST'])
@student_required
def create():
    """
    GET  – Render the new portfolio form.
    POST – Validate and insert a new portfolio record.
    """
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not title:
            flash("Portfolio title is required.", "danger")
            return render_template('portfolios/create.html'), 400

        if len(title) > 100:
            flash("Title must be 100 characters or fewer.", "danger")
            return render_template('portfolios/create.html'), 400

        db = get_db()
        now = datetime.utcnow().isoformat()

        cursor = db.execute(
            """
            INSERT INTO portfolios
                (student_id, title, description, created_date, updated_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session['user_id'], title, description or None, now, now)
        )
        db.commit()
        new_id = cursor.lastrowid

        log_action(session['user_id'], "portfolio_create",
                   f"Created portfolio ID {new_id}: '{title}'")

        flash(f"Portfolio '{title}' created successfully!", "success")
        return redirect(url_for('portfolios.view', portfolio_id=new_id))

    return render_template('portfolios/create.html')


@portfolios_bp.route('/<int:portfolio_id>')
@login_required
def view(portfolio_id):
    """
    Display a portfolio and all its ordered artworks.
    Students can only view their own; teachers can view any.
    """
    db = get_db()

    portfolio = db.execute(
        """
        SELECT p.*, u.first_name, u.last_name
        FROM portfolios p
        JOIN users u ON u.user_id = p.student_id
        WHERE p.portfolio_id = ?
        """,
        (portfolio_id,)
    ).fetchone()

    if portfolio is None:
        flash("Portfolio not found.", "warning")
        return redirect(url_for('student.dashboard'))

    if session['role'] == 'student' and portfolio['student_id'] != session['user_id']:
        flash("You do not have permission to view that portfolio.", "danger")
        return redirect(url_for('student.dashboard'))

    # Fetch artworks in display order
    artworks = db.execute(
        """
        SELECT a.*, pa.display_order
        FROM artworks a
        JOIN portfolio_artworks pa ON pa.artwork_id = a.artwork_id
        WHERE pa.portfolio_id = ?
        ORDER BY pa.display_order ASC
        """,
        (portfolio_id,)
    ).fetchall()

    # Artworks that belong to this student but are NOT in this portfolio
    if session['role'] == 'student':
        available_artworks = db.execute(
            """
            SELECT * FROM artworks
            WHERE student_id = ?
              AND artwork_id NOT IN (
                  SELECT artwork_id FROM portfolio_artworks
                  WHERE portfolio_id = ?
              )
            ORDER BY upload_date DESC
            """,
            (session['user_id'], portfolio_id)
        ).fetchall()
    else:
        available_artworks = []

    return render_template(
        'portfolios/view.html',
        portfolio=portfolio,
        artworks=artworks,
        available_artworks=available_artworks
    )


@portfolios_bp.route('/<int:portfolio_id>/edit', methods=['GET', 'POST'])
@student_required
def edit(portfolio_id):
    """Edit portfolio title and description."""
    db = get_db()

    portfolio = db.execute(
        "SELECT * FROM portfolios WHERE portfolio_id = ? AND student_id = ?",
        (portfolio_id, session['user_id'])
    ).fetchone()

    if portfolio is None:
        flash("Portfolio not found.", "warning")
        return redirect(url_for('portfolios.index'))

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not title:
            flash("Portfolio title is required.", "danger")
            return render_template('portfolios/edit.html', portfolio=portfolio), 400

        if len(title) > 100:
            flash("Title must be 100 characters or fewer.", "danger")
            return render_template('portfolios/edit.html', portfolio=portfolio), 400

        db.execute(
            """
            UPDATE portfolios
            SET title = ?, description = ?, updated_date = ?
            WHERE portfolio_id = ?
            """,
            (title, description or None,
             datetime.utcnow().isoformat(), portfolio_id)
        )
        db.commit()

        log_action(session['user_id'], "portfolio_edit",
                   f"Edited portfolio ID {portfolio_id}")

        flash("Portfolio updated successfully.", "success")
        return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))

    return render_template('portfolios/edit.html', portfolio=portfolio)


@portfolios_bp.route('/<int:portfolio_id>/delete', methods=['POST'])
@student_required
def delete(portfolio_id):
    """Delete a portfolio and all its artwork relationships."""
    db = get_db()

    portfolio = db.execute(
        "SELECT * FROM portfolios WHERE portfolio_id = ? AND student_id = ?",
        (portfolio_id, session['user_id'])
    ).fetchone()

    if portfolio is None:
        flash("Portfolio not found.", "warning")
        return redirect(url_for('portfolios.index'))

    # Cascade delete handled by SQLite foreign key ON DELETE CASCADE
    db.execute("DELETE FROM portfolios WHERE portfolio_id = ?", (portfolio_id,))
    db.commit()

    log_action(session['user_id'], "portfolio_delete",
               f"Deleted portfolio ID {portfolio_id}: '{portfolio['title']}'")

    flash(f"Portfolio '{portfolio['title']}' has been deleted.", "info")
    return redirect(url_for('portfolios.index'))


@portfolios_bp.route('/<int:portfolio_id>/add_artwork', methods=['POST'])
@student_required
def add_artwork(portfolio_id):
    """Add an artwork to a portfolio."""
    db = get_db()

    portfolio = db.execute(
        "SELECT * FROM portfolios WHERE portfolio_id = ? AND student_id = ?",
        (portfolio_id, session['user_id'])
    ).fetchone()

    if portfolio is None:
        flash("Portfolio not found.", "danger")
        return redirect(url_for('portfolios.index'))

    artwork_id = request.form.get('artwork_id', type=int)

    if not artwork_id:
        flash("Please select an artwork to add.", "danger")
        return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))

    # Verify the artwork belongs to this student
    artwork = db.execute(
        "SELECT * FROM artworks WHERE artwork_id = ? AND student_id = ?",
        (artwork_id, session['user_id'])
    ).fetchone()

    if artwork is None:
        flash("Artwork not found.", "danger")
        return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))

    # Check not already in portfolio
    existing = db.execute(
        "SELECT 1 FROM portfolio_artworks WHERE portfolio_id = ? AND artwork_id = ?",
        (portfolio_id, artwork_id)
    ).fetchone()

    if existing:
        flash("That artwork is already in this portfolio.", "warning")
        return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))

    # Get next display order
    max_order = db.execute(
        "SELECT MAX(display_order) FROM portfolio_artworks WHERE portfolio_id = ?",
        (portfolio_id,)
    ).fetchone()[0] or 0

    db.execute(
        "INSERT INTO portfolio_artworks (portfolio_id, artwork_id, display_order) VALUES (?, ?, ?)",
        (portfolio_id, artwork_id, max_order + 1)
    )
    db.execute(
        "UPDATE portfolios SET updated_date = ? WHERE portfolio_id = ?",
        (datetime.utcnow().isoformat(), portfolio_id)
    )
    db.commit()

    log_action(session['user_id'], "portfolio_add_artwork",
               f"Added artwork {artwork_id} to portfolio {portfolio_id}")

    flash(f"'{artwork['title']}' added to portfolio.", "success")
    return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))


@portfolios_bp.route('/<int:portfolio_id>/remove_artwork', methods=['POST'])
@student_required
def remove_artwork(portfolio_id):
    """Remove an artwork from a portfolio."""
    db = get_db()

    portfolio = db.execute(
        "SELECT * FROM portfolios WHERE portfolio_id = ? AND student_id = ?",
        (portfolio_id, session['user_id'])
    ).fetchone()

    if portfolio is None:
        flash("Portfolio not found.", "danger")
        return redirect(url_for('portfolios.index'))

    artwork_id = request.form.get('artwork_id', type=int)

    db.execute(
        "DELETE FROM portfolio_artworks WHERE portfolio_id = ? AND artwork_id = ?",
        (portfolio_id, artwork_id)
    )
    db.execute(
        "UPDATE portfolios SET updated_date = ? WHERE portfolio_id = ?",
        (datetime.utcnow().isoformat(), portfolio_id)
    )
    db.commit()

    log_action(session['user_id'], "portfolio_remove_artwork",
               f"Removed artwork {artwork_id} from portfolio {portfolio_id}")

    flash("Artwork removed from portfolio.", "info")
    return redirect(url_for('portfolios.view', portfolio_id=portfolio_id))


@portfolios_bp.route('/<int:portfolio_id>/reorder', methods=['POST'])
@student_required
def reorder(portfolio_id):
    """
    Update the display order of artworks in a portfolio.
    Expects JSON body: { "order": [artwork_id_1, artwork_id_2, ...] }
    """
    db = get_db()

    portfolio = db.execute(
        "SELECT * FROM portfolios WHERE portfolio_id = ? AND student_id = ?",
        (portfolio_id, session['user_id'])
    ).fetchone()

    if portfolio is None:
        return jsonify({"status": "error", "message": "Portfolio not found."}), 404

    data = request.get_json()
    if not data or 'order' not in data:
        return jsonify({"status": "error", "message": "Missing order list."}), 400

    for position, artwork_id in enumerate(data['order'], start=1):
        db.execute(
            """
            UPDATE portfolio_artworks
            SET display_order = ?
            WHERE portfolio_id = ? AND artwork_id = ?
            """,
            (position, portfolio_id, artwork_id)
        )

    db.execute(
        "UPDATE portfolios SET updated_date = ? WHERE portfolio_id = ?",
        (datetime.utcnow().isoformat(), portfolio_id)
    )
    db.commit()

    return jsonify({"status": "success", "message": "Order saved."}), 200


# ---------------------------------------------------------------------------
# Teacher view: browse student portfolios
# ---------------------------------------------------------------------------

@portfolios_bp.route('/all')
@teacher_required
def teacher_all():
    """List all student portfolios for teacher review."""
    db = get_db()
    portfolios = db.execute(
        """
        SELECT p.*, u.first_name, u.last_name,
               COUNT(a.artwork_id) AS artwork_count
        FROM portfolios p
        JOIN users u ON u.user_id = p.student_id
        LEFT JOIN portfolio_artworks pa ON pa.portfolio_id = p.portfolio_id
        LEFT JOIN artworks a            ON a.artwork_id    = pa.artwork_id
        GROUP BY p.portfolio_id
        ORDER BY u.last_name, u.first_name, p.created_date DESC
        """
    ).fetchall()

    return render_template('portfolios/teacher_all.html', portfolios=portfolios)