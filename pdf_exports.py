import os
from datetime import datetime

from flask import (
    Blueprint, session, redirect, url_for,
    flash, current_app, send_from_directory
)

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from auth import get_db, login_required, log_action

# ---------------------------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------------------------

pdf_exports_bp = Blueprint('pdf_exports', __name__, url_prefix='/pdf')

# ---------------------------------------------------------------------------
# Helper function
# ---------------------------------------------------------------------------

def draw_wrapped_text(pdf_canvas, text, x, y, max_chars=90, line_height=12):
    """
    Draw wrapped text on the PDF and return the updated y position.
    """
    if not text:
        return y

    words = text.split()
    line = ""

    for word in words:
        test_line = f"{line} {word}".strip()

        if len(test_line) > max_chars:
            pdf_canvas.drawString(x, y, line)
            y -= line_height
            line = word
        else:
            line = test_line

    if line:
        pdf_canvas.drawString(x, y, line)
        y -= line_height

    return y


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pdf_exports_bp.route('/portfolio/<int:portfolio_id>')
@login_required
def export_portfolio(portfolio_id):
    """
    Generate and download a PDF export for a student portfolio.
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
        return redirect(url_for('auth.dashboard'))

    if session.get('role') == 'student' and portfolio['student_id'] != session.get('user_id'):
        flash("You do not have permission to export this portfolio.", "danger")
        return redirect(url_for('student.dashboard'))

    artworks = db.execute(
        """
        SELECT a.*
        FROM portfolio_artworks pa
        JOIN artworks a ON a.artwork_id = pa.artwork_id
        WHERE pa.portfolio_id = ?
        ORDER BY pa.display_order ASC, pa.added_date ASC
        """,
        (portfolio_id,)
    ).fetchall()

    export_folder = current_app.config.get(
        'PDF_EXPORT_FOLDER',
        os.path.join('static', 'pdf_exports')
    )

    os.makedirs(export_folder, exist_ok=True)

    file_name = f"portfolio_{portfolio_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    file_path = os.path.join(export_folder, file_name)

    pdf = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - inch

    # -----------------------------------------------------------------------
    # PDF Header
    # -----------------------------------------------------------------------

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(inch, y, portfolio['title'])
    y -= 26

    pdf.setFont("Helvetica", 12)
    pdf.drawString(
        inch,
        y,
        f"Student: {portfolio['first_name']} {portfolio['last_name']}"
    )
    y -= 20

    if portfolio['description']:
        pdf.setFont("Helvetica", 10)
        y = draw_wrapped_text(
            pdf,
            f"Description: {portfolio['description']}",
            inch,
            y,
            max_chars=90,
            line_height=12
        )
        y -= 10

    pdf.line(inch, y, width - inch, y)
    y -= 25

    # -----------------------------------------------------------------------
    # Empty portfolio message
    # -----------------------------------------------------------------------

    if not artworks:
        pdf.setFont("Helvetica", 12)
        pdf.drawString(inch, y, "No artwork has been added to this portfolio yet.")

    # -----------------------------------------------------------------------
    # Artwork pages/content
    # -----------------------------------------------------------------------

    for artwork in artworks:
        if y < 2.5 * inch:
            pdf.showPage()
            y = height - inch

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(inch, y, artwork['title'])
        y -= 18

        pdf.setFont("Helvetica", 10)

        grade_text = "Pending"
        if artwork['grade'] is not None:
            grade_text = f"{artwork['grade']}%"

        pdf.drawString(
            inch,
            y,
            f"Medium: {artwork['medium']}    Grade: {grade_text}"
        )
        y -= 16

        if artwork['description']:
            y = draw_wrapped_text(
                pdf,
                f"Description: {artwork['description']}",
                inch,
                y,
                max_chars=95,
                line_height=12
            )
            y -= 8

        image_path = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            artwork['file_path']
        )

        if os.path.exists(image_path):
            try:
                pdf.drawImage(
                    image_path,
                    inch,
                    y - 2.4 * inch,
                    width=3.2 * inch,
                    height=2.2 * inch,
                    preserveAspectRatio=True,
                    anchor='nw'
                )
                y -= 2.65 * inch
            except Exception:
                pdf.drawString(inch, y, "[Image could not be added to PDF]")
                y -= 16

        comments = db.execute(
            """
            SELECT c.comment_text,
                   u.first_name || ' ' || u.last_name AS teacher_name
            FROM comments c
            JOIN users u ON u.user_id = c.teacher_id
            WHERE c.artwork_id = ?
            ORDER BY c.created_at DESC
            """,
            (artwork['artwork_id'],)
        ).fetchall()

        if comments:
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(inch, y, "Teacher Feedback:")
            y -= 14

            pdf.setFont("Helvetica", 9)

            for comment in comments:
                if y < inch:
                    pdf.showPage()
                    y = height - inch

                y = draw_wrapped_text(
                    pdf,
                    f"{comment['teacher_name']}: {comment['comment_text']}",
                    inch,
                    y,
                    max_chars=100,
                    line_height=11
                )
                y -= 4

        y -= 18

    pdf.save()

    # -----------------------------------------------------------------------
    # Save export record in database
    # -----------------------------------------------------------------------

    db.execute(
        """
        INSERT INTO pdf_exports
            (portfolio_id, file_name, file_path, generated_date)
        VALUES (?, ?, ?, ?)
        """,
        (
            portfolio_id,
            file_name,
            file_path,
            datetime.utcnow().isoformat()
        )
    )

    db.commit()

    log_action(
        session.get('user_id'),
        "pdf_export",
        f"Generated PDF export for portfolio ID {portfolio_id}"
    )

    return send_from_directory(
        export_folder,
        file_name,
        as_attachment=True
    )