import os
import uuid
from datetime import datetime

from flask import (
    Blueprint, request, session, redirect,
    url_for, render_template, flash, jsonify,
    current_app, send_from_directory, g
)
from werkzeug.utils import secure_filename
from PIL import Image

from auth import get_db, login_required, student_required, log_action

# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------

artworks_bp = Blueprint('artworks', __name__, url_prefix='/artworks')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_IMAGE_DIMENSION = 1920   # pixels — resize larger images to this width/height
THUMBNAIL_SIZE      = (400, 400)
MEDIUM_CHOICES = [
    'Pencil', 'Charcoal', 'Colored Pencil',
    'Watercolor', 'Acrylic', 'Digital', 'Other'
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    """Return True if the file extension is in the allowed set."""
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_and_compress_image(file_storage, upload_folder):
    """
    Save an uploaded image to disk.
    - Resize if larger than MAX_IMAGE_DIMENSION on either axis.
    - Save a thumbnail alongside the main image.
    - Returns (stored_filename, thumbnail_filename).
    """
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    unique_name   = f"{uuid.uuid4().hex}.{ext}"
    thumb_name    = f"thumb_{unique_name}"

    full_path  = os.path.join(upload_folder, unique_name)
    thumb_path = os.path.join(upload_folder, thumb_name)

    img = Image.open(file_storage.stream)

    # Convert RGBA/palette images to RGB for JPEG compatibility
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    # Resize main image if it exceeds the max dimension
    w, h = img.size
    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

    img.save(full_path, optimize=True, quality=85)

    # Create thumbnail
    thumb = img.copy()
    thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
    thumb.save(thumb_path, optimize=True, quality=80)

    return unique_name, thumb_name


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@artworks_bp.route('/upload', methods=['GET', 'POST'])
@student_required
def upload():
    """
    GET  – Render the artwork upload form.
    POST – Validate the file and metadata, compress the image, store it,
           and insert an artwork record into the database.
    """
    if request.method == 'POST':
        # --- File presence check ---
        if 'artwork_file' not in request.files:
            flash("No file was included in the upload.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        file = request.files['artwork_file']

        if file.filename == '':
            flash("Please select a file before submitting.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        # --- File type check ---
        if not allowed_file(file.filename):
            flash("Only JPG and PNG files are accepted.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        # --- Metadata validation ---
        title       = request.form.get('title', '').strip()
        medium      = request.form.get('medium', '').strip()
        description = request.form.get('description', '').strip()

        if not title:
            flash("Artwork title is required.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        if len(title) > 200:
            flash("Title must be 200 characters or fewer.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        if medium not in MEDIUM_CHOICES:
            flash("Please select a valid medium.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        if len(description) > 1000:
            flash("Description must be 1000 characters or fewer.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 400

        # --- Save and compress image ---
        upload_folder = current_app.config['UPLOAD_FOLDER']
        try:
            stored_name, thumb_name = save_and_compress_image(file, upload_folder)
        except Exception as e:
            flash("Image processing failed. Please try a different file.", "danger")
            return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES), 500

        # --- Insert into database ---
        db = get_db()
        student_id = session['user_id']
        upload_date = datetime.utcnow().isoformat()

        cursor = db.execute(
            """
            INSERT INTO artworks
                (student_id, title, description, file_path,
                 upload_date, medium, is_public)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (student_id, title, description or None,
             stored_name, upload_date, medium)
        )
        db.commit()
        new_artwork_id = cursor.lastrowid

        log_action(student_id, "artwork_upload",
                   f"Uploaded artwork ID {new_artwork_id}: '{title}'")

        flash(f"'{title}' uploaded successfully!", "success")
        return redirect(url_for('student.dashboard'))

    # GET
    return render_template('artworks/upload.html', mediums=MEDIUM_CHOICES)


@artworks_bp.route('/<int:artwork_id>')
@login_required
def detail(artwork_id):
    """
    Display a single artwork with its metadata and teacher feedback.
    Students can only view their own artwork; teachers can view any.
    """
    db = get_db()

    artwork = db.execute(
        """
        SELECT a.*, u.first_name, u.last_name
        FROM artworks a
        JOIN users u ON u.user_id = a.student_id
        WHERE a.artwork_id = ?
        """,
        (artwork_id,)
    ).fetchone()

    if artwork is None:
        flash("Artwork not found.", "warning")
        return redirect(url_for('student.dashboard'))

    # Access control: students can only see their own artwork
    if session['role'] == 'student' and artwork['student_id'] != session['user_id']:
        flash("You do not have permission to view that artwork.", "danger")
        return redirect(url_for('student.dashboard'))

    # Fetch feedback / comments for this artwork
    feedback = db.execute(
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
        'artworks/detail.html',
        artwork=artwork,
        feedback=feedback
    )


@artworks_bp.route('/<int:artwork_id>/delete', methods=['POST'])
@student_required
def delete(artwork_id):
    """
    Delete an artwork record and its stored file.
    Only the owning student may delete their own artwork.
    """
    db = get_db()
    student_id = session['user_id']

    artwork = db.execute(
        "SELECT * FROM artworks WHERE artwork_id = ? AND student_id = ?",
        (artwork_id, student_id)
    ).fetchone()

    if artwork is None:
        flash("Artwork not found or you do not have permission to delete it.", "danger")
        return redirect(url_for('student.dashboard'))

    # Remove the file from disk
    upload_folder = current_app.config['UPLOAD_FOLDER']
    for filename in (artwork['file_path'], f"thumb_{artwork['file_path']}"):
        file_path = os.path.join(upload_folder, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.execute("DELETE FROM artworks WHERE artwork_id = ?", (artwork_id,))
    db.commit()

    log_action(student_id, "artwork_delete",
               f"Deleted artwork ID {artwork_id}: '{artwork['title']}'")

    flash(f"'{artwork['title']}' has been deleted.", "info")
    return redirect(url_for('student.dashboard'))


@artworks_bp.route('/<int:artwork_id>/toggle_public', methods=['POST'])
@student_required
def toggle_public(artwork_id):
    """Toggle an artwork's public/private visibility."""
    db = get_db()
    student_id = session['user_id']

    artwork = db.execute(
        "SELECT * FROM artworks WHERE artwork_id = ? AND student_id = ?",
        (artwork_id, student_id)
    ).fetchone()

    if artwork is None:
        flash("Artwork not found.", "danger")
        return redirect(url_for('student.dashboard'))

    new_status = 0 if artwork['is_public'] else 1
    db.execute(
        "UPDATE artworks SET is_public = ? WHERE artwork_id = ?",
        (new_status, artwork_id)
    )
    db.commit()

    status_label = "public" if new_status else "private"
    flash(f"'{artwork['title']}' is now {status_label}.", "success")
    return redirect(url_for('artworks.detail', artwork_id=artwork_id))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@artworks_bp.route('/api/artworks', methods=['GET'])
@login_required
def api_list():
    """
    GET /api/artworks
    Return artworks filtered by the logged-in student's user_id.
    Teachers receive all artworks.
    """
    db = get_db()
    if session['role'] == 'student':
        rows = db.execute(
            "SELECT * FROM artworks WHERE student_id = ? ORDER BY upload_date DESC",
            (session['user_id'],)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM artworks ORDER BY upload_date DESC"
        ).fetchall()

    return jsonify({
        "status": "success",
        "data": [dict(row) for row in rows]
    }), 200


@artworks_bp.route('/api/artworks/<int:artwork_id>', methods=['GET'])
@login_required
def api_detail(artwork_id):
    """GET /api/artworks/:id — return a single artwork record."""
    db = get_db()
    artwork = db.execute(
        "SELECT * FROM artworks WHERE artwork_id = ?", (artwork_id,)
    ).fetchone()

    if artwork is None:
        return jsonify({"status": "error", "message": "Artwork not found."}), 404

    if session['role'] == 'student' and artwork['student_id'] != session['user_id']:
        return jsonify({"status": "error", "message": "Access denied."}), 403

    return jsonify({"status": "success", "data": dict(artwork)}), 200


@artworks_bp.route('/api/artworks/<int:artwork_id>', methods=['DELETE'])
@student_required
def api_delete(artwork_id):
    """DELETE /api/artworks/:id — delete artwork (owner only)."""
    db = get_db()
    artwork = db.execute(
        "SELECT * FROM artworks WHERE artwork_id = ? AND student_id = ?",
        (artwork_id, session['user_id'])
    ).fetchone()

    if artwork is None:
        return jsonify({"status": "error", "message": "Artwork not found or access denied."}), 404

    upload_folder = current_app.config['UPLOAD_FOLDER']
    for filename in (artwork['file_path'], f"thumb_{artwork['file_path']}"):
        fp = os.path.join(upload_folder, filename)
        if os.path.exists(fp):
            os.remove(fp)

    db.execute("DELETE FROM artworks WHERE artwork_id = ?", (artwork_id,))
    db.commit()
    log_action(session['user_id'], "api_artwork_delete", f"Deleted artwork {artwork_id}")

    return jsonify({"status": "success", "message": "Artwork deleted."}), 200