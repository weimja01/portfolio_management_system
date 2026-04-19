import os
from datetime import timedelta
from flask import Flask


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

    # File upload settings
    app.config['UPLOAD_FOLDER']    = os.path.join('static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB max upload

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join('static', 'pdf_exports'), exist_ok=True)

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

    from integration_tests import tests_bp
    app.register_blueprint(tests_bp)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)