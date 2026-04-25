import os
from datetime import timedelta
from flask import Flask


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    app.secret_key = 'completely-new-random-key-12345'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

    # File upload settings
    app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
    app.config['PDF_EXPORT_FOLDER'] = os.path.join('static', 'pdf_exports')
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB max upload

    # Ensure upload and PDF export directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PDF_EXPORT_FOLDER'], exist_ok=True)

    # -----------------------------------------------------------------------
    # Register blueprints
    # -----------------------------------------------------------------------
    from auth import init_app as init_auth
    init_auth(app)

    from artworks import artworks_bp
    app.register_blueprint(artworks_bp)

    from portfolios import portfolios_bp
    app.register_blueprint(portfolios_bp)

    from student import student_bp
    app.register_blueprint(student_bp)

    from teacher import teacher_bp
    app.register_blueprint(teacher_bp)

    from pdf_exports import pdf_exports_bp
    app.register_blueprint(pdf_exports_bp)

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    @app.route('/session-debug')
    def session_debug():
        """Debug route to see session contents."""
        from flask import session

        session_data = dict(session)

        html = "<h1>Session Debug</h1>"
        html += "<h2>Session Data:</h2>"

        if session_data:
            html += "<ul>"
            for key, value in session_data.items():
                html += f"<li><strong>{key}:</strong> {value}</li>"
            html += "</ul>"
        else:
            html += "<p style='color: green; font-size: 20px;'>✓ Session is EMPTY (not logged in)</p>"

        html += "<br><hr><br>"
        html += "<a href='/auth/login'>Login</a> | "
        html += "<a href='/auth/register'>Register</a>"

        return html

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)