import os
import io
import sys
import unittest
import tempfile

# Make sure the project root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from auth import get_db
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Base test class — spins up a fresh in-memory database for each test
# ---------------------------------------------------------------------------

class BaseTestCase(unittest.TestCase):
    """Shared setup/teardown for all integration tests."""

    def setUp(self):
        """Create a test Flask app with an isolated temp database."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')

        self.app = create_app()
        self.app.config.update({
            'TESTING':          True,
            'DATABASE':         self.db_path,
            'WTF_CSRF_ENABLED': False,
            'UPLOAD_FOLDER':    tempfile.mkdtemp(),
        })

        self.client = self.app.test_client()

        # Initialize schema inside app context
        with self.app.app_context():
            self._init_db()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _init_db(self):
        """Create tables and seed test users."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student','teacher','admin')),
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                grad_year INTEGER,
                department TEXT,
                account_status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS artworks (
                artwork_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                file_path TEXT NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                medium TEXT NOT NULL,
                grade REAL,
                is_public BOOLEAN DEFAULT 0,
                FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                artwork_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                comment_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE,
                FOREIGN KEY (teacher_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS portfolios (
                portfolio_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS portfolio_artworks (
                portfolio_id INTEGER NOT NULL,
                artwork_id   INTEGER NOT NULL,
                display_order INTEGER DEFAULT 0,
                PRIMARY KEY (portfolio_id, artwork_id),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
                FOREIGN KEY (artwork_id)   REFERENCES artworks(artwork_id)    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT NOT NULL,
                action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_artworks_student ON artworks(student_id);
            CREATE INDEX IF NOT EXISTS idx_comments_artwork ON comments(artwork_id);
        ''')

        # Seed users
        student_hash = generate_password_hash('Student123!')
        teacher_hash = generate_password_hash('Teacher123!')
        admin_hash   = generate_password_hash('Admin123!')

        conn.execute(
            "INSERT INTO users (username,email,password_hash,role,first_name,last_name) VALUES (?,?,?,?,?,?)",
            ('student1', 'student@test.com', student_hash, 'student', 'Art', 'Student')
        )
        conn.execute(
            "INSERT INTO users (username,email,password_hash,role,first_name,last_name) VALUES (?,?,?,?,?,?)",
            ('teacher1', 'teacher@test.com', teacher_hash, 'teacher', 'Ms', 'Teacher')
        )
        conn.execute(
            "INSERT INTO users (username,email,password_hash,role,first_name,last_name) VALUES (?,?,?,?,?,?)",
            ('admin1', 'admin@test.com', admin_hash, 'admin', 'Site', 'Admin')
        )
        conn.commit()
        conn.close()

    def login(self, email, password):
        return self.client.post('/auth/login', data={
            'email':    email,
            'password': password
        }, follow_redirects=True)

    def logout(self):
        return self.client.post('/auth/logout', follow_redirects=True)

    def _fake_image(self, filename='test.jpg'):
        """Return a minimal in-memory JPEG-like file for upload tests."""
        from PIL import Image
        img = Image.new('RGB', (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return (buf, filename)


# ===========================================================================
# TC-1: Authentication and User Access
# ===========================================================================

class TestAuthentication(BaseTestCase):

    def test_register_valid_account(self):
        """TC-AUTH-1: Valid registration creates a new account."""
        resp = self.client.post('/auth/register', data={
            'first_name':       'New',
            'last_name':        'User',
            'username':         'newuser',
            'email':            'new@test.com',
            'password':         'ValidPass1!',
            'confirm_password': 'ValidPass1!',
            'role':             'student'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'log in', resp.data.lower())

    def test_register_missing_required_fields(self):
        """TC-AUTH-2: Registration rejects missing required fields."""
        resp = self.client.post('/auth/register', data={
            'first_name': '',
            'last_name':  '',
            'username':   '',
            'email':      '',
            'password':   '',
            'confirm_password': '',
            'role':       ''
        }, follow_redirects=True)
        self.assertIn(resp.status_code, [400, 200])
        self.assertIn(b'required', resp.data.lower())

    def test_register_duplicate_email(self):
        """TC-AUTH-3: Registration rejects a duplicate email address."""
        self.client.post('/auth/register', data={
            'first_name': 'Dup', 'last_name': 'User',
            'username': 'dupuser', 'email': 'student@test.com',
            'password': 'ValidPass1!', 'confirm_password': 'ValidPass1!',
            'role': 'student'
        })
        resp = self.client.post('/auth/register', data={
            'first_name': 'Dup2', 'last_name': 'User2',
            'username': 'dupuser2', 'email': 'student@test.com',
            'password': 'ValidPass1!', 'confirm_password': 'ValidPass1!',
            'role': 'student'
        }, follow_redirects=True)
        self.assertIn(b'already exists', resp.data.lower())

    def test_login_valid_credentials(self):
        """TC-AUTH-4: Valid credentials authenticate user and redirect to dashboard."""
        resp = self.login('student@test.com', 'Student123!')
        self.assertEqual(resp.status_code, 200)

    def test_login_invalid_credentials(self):
        """TC-AUTH-5: Invalid password denies access with an error message."""
        resp = self.login('student@test.com', 'WrongPassword')
        self.assertIn(b'invalid', resp.data.lower())

    def test_role_based_redirect_student(self):
        """TC-AUTH-6a: Student is redirected to student dashboard."""
        resp = self.login('student@test.com', 'Student123!')
        self.assertIn(b'dashboard', resp.data.lower())

    def test_role_based_redirect_teacher(self):
        """TC-AUTH-6b: Teacher is redirected to teacher dashboard."""
        resp = self.login('teacher@test.com', 'Teacher123!')
        self.assertEqual(resp.status_code, 200)

    def test_logout_ends_session(self):
        """TC-AUTH-7: Logout clears session; protected pages redirect to login."""
        self.login('student@test.com', 'Student123!')
        self.logout()
        resp = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'log in', resp.data.lower())

    def test_password_stored_as_hash(self):
        """TC-AUTH-8: Stored password is a hash, not plain text."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT password_hash FROM users WHERE email = 'student@test.com'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[0], 'Student123!')
        self.assertTrue(row[0].startswith('scrypt:') or row[0].startswith('pbkdf2:') or
                        row[0].startswith('$2b$'))


# ===========================================================================
# TC-2: Artwork Upload and File Validation
# ===========================================================================

class TestArtworkUpload(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login('student@test.com', 'Student123!')

    def test_upload_valid_jpg(self):
        """TC-UPLOAD-1: Valid JPG file uploads successfully."""
        buf, fname = self._fake_image('art.jpg')
        resp = self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title':        'My Red Painting',
            'medium':       'Acrylic',
            'description':  'A test artwork'
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'uploaded successfully', resp.data.lower())

    def test_upload_invalid_file_type(self):
        """TC-UPLOAD-2: Unsupported file type is rejected."""
        buf = io.BytesIO(b'%PDF-1.4 fake pdf content')
        resp = self.client.post('/artworks/upload', data={
            'artwork_file': (buf, 'document.pdf'),
            'title':        'Bad File',
            'medium':       'Acrylic',
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'jpg', resp.data.lower())

    def test_upload_missing_title(self):
        """TC-UPLOAD-3: Upload without title is rejected with validation error."""
        buf, fname = self._fake_image()
        resp = self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title':        '',
            'medium':       'Acrylic',
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b'required', resp.data.lower())

    def test_upload_stores_metadata(self):
        """TC-UPLOAD-4: Artwork metadata is stored in the database."""
        buf, fname = self._fake_image()
        self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title':        'Meta Test',
            'medium':       'Watercolor',
            'description':  'Testing metadata storage'
        }, content_type='multipart/form-data', follow_redirects=True)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM artworks WHERE title = 'Meta Test'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_upload_records_upload_date(self):
        """TC-UPLOAD-5: Upload date is recorded with each artwork."""
        buf, fname = self._fake_image()
        self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title': 'Date Test', 'medium': 'Pencil'
        }, content_type='multipart/form-data', follow_redirects=True)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT upload_date FROM artworks WHERE title = 'Date Test'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0])


# ===========================================================================
# TC-3: Portfolio Management
# ===========================================================================

class TestPortfolioManagement(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login('student@test.com', 'Student123!')

    def _create_portfolio(self, title='Test Portfolio'):
        return self.client.post('/portfolios/create', data={
            'title':       title,
            'description': 'A test portfolio'
        }, follow_redirects=True)

    def _upload_artwork(self, title='Test Art'):
        buf, fname = self._fake_image()
        return self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title': title, 'medium': 'Pencil'
        }, content_type='multipart/form-data', follow_redirects=True)

    def test_create_portfolio(self):
        """TC-PORT-1: Student can create a portfolio."""
        resp = self._create_portfolio('Senior Exhibition')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'senior exhibition', resp.data.lower())

    def test_edit_portfolio(self):
        """TC-PORT-2: Student can edit a portfolio title and description."""
        self._create_portfolio('Original Title')
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT portfolio_id FROM portfolios WHERE title='Original Title'").fetchone()
        conn.close()
        pid = row[0]

        resp = self.client.post(f'/portfolios/{pid}/edit', data={
            'title':       'Updated Title',
            'description': 'Updated description'
        }, follow_redirects=True)
        self.assertIn(b'updated', resp.data.lower())

    def test_delete_portfolio(self):
        """TC-PORT-3: Student can delete a portfolio."""
        self._create_portfolio('To Delete')
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT portfolio_id FROM portfolios WHERE title='To Delete'").fetchone()
        conn.close()
        pid = row[0]

        self.client.post(f'/portfolios/{pid}/delete', follow_redirects=True)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM portfolios WHERE portfolio_id=?", (pid,)).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_add_artwork_to_portfolio(self):
        """TC-PORT-4: Student can add artwork to a portfolio."""
        self._create_portfolio()
        self._upload_artwork('Portfolio Art')

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        pid = conn.execute("SELECT portfolio_id FROM portfolios LIMIT 1").fetchone()[0]
        aid = conn.execute("SELECT artwork_id FROM artworks WHERE title='Portfolio Art'").fetchone()[0]
        conn.close()

        resp = self.client.post(f'/portfolios/{pid}/add_artwork',
                                data={'artwork_id': aid}, follow_redirects=True)
        self.assertIn(b'added', resp.data.lower())

    def test_remove_artwork_from_portfolio(self):
        """TC-PORT-5: Student can remove artwork from a portfolio."""
        self._create_portfolio()
        self._upload_artwork('Remove Me')

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        pid = conn.execute("SELECT portfolio_id FROM portfolios LIMIT 1").fetchone()[0]
        aid = conn.execute("SELECT artwork_id FROM artworks WHERE title='Remove Me'").fetchone()[0]
        conn.close()

        self.client.post(f'/portfolios/{pid}/add_artwork', data={'artwork_id': aid})
        resp = self.client.post(f'/portfolios/{pid}/remove_artwork',
                                data={'artwork_id': aid}, follow_redirects=True)
        self.assertIn(b'removed', resp.data.lower())


# ===========================================================================
# TC-4: Security and Access Control
# ===========================================================================

class TestSecurityAccessControl(BaseTestCase):

    def test_protected_page_redirects_without_login(self):
        """TC-SEC-1: Unauthenticated access to dashboard redirects to login."""
        resp = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'log in', resp.data.lower())

    def test_student_cannot_access_teacher_routes(self):
        """TC-SEC-2: Student cannot access teacher-only pages."""
        self.login('student@test.com', 'Student123!')
        resp = self.client.get('/portfolios/all', follow_redirects=True)
        # Should redirect or show access denied
        self.assertIn(resp.status_code, [200, 302, 403])
        denied = b'access denied' in resp.data.lower() or b'log in' in resp.data.lower()
        self.assertTrue(denied or resp.status_code in [302, 403])

    def test_session_cleared_after_logout(self):
        """TC-SEC-3: Session is cleared on logout; re-authentication required."""
        self.login('student@test.com', 'Student123!')
        self.logout()
        resp = self.client.get('/student/dashboard', follow_redirects=True)
        self.assertIn(b'log in', resp.data.lower())

    def test_student_cannot_delete_another_students_artwork(self):
        """TC-SEC-4: Student cannot delete artwork they do not own."""
        # Upload as student1
        self.login('student@test.com', 'Student123!')
        buf, fname = self._fake_image()
        self.client.post('/artworks/upload', data={
            'artwork_file': (buf, fname),
            'title': 'Protected Art', 'medium': 'Pencil'
        }, content_type='multipart/form-data')

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        aid = conn.execute("SELECT artwork_id FROM artworks WHERE title='Protected Art'").fetchone()[0]
        conn.close()

        # Try to delete as a second student account (not the owner)
        self.logout()
        # Register a second student
        self.client.post('/auth/register', data={
            'first_name': 'Other', 'last_name': 'Student',
            'username': 'student2', 'email': 'student2@test.com',
            'password': 'Student123!', 'confirm_password': 'Student123!',
            'role': 'student'
        })
        self.login('student2@test.com', 'Student123!')
        resp = self.client.post(f'/artworks/{aid}/delete', follow_redirects=True)
        # Should not allow deletion
        self.assertNotIn(b'deleted', resp.data.lower())


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Portfolio Management System — Integration Test Suite")
    print("Author: Suhail Solim | SDEV 265")
    print("=" * 60)
    unittest.main(verbosity=2)