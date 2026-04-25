import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

# Enable foreign key enforcement
cursor.execute("PRAGMA foreign_keys = ON")

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

cursor.executescript('''
    -- USERS table
    CREATE TABLE IF NOT EXISTS users (
        user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        username       TEXT    NOT NULL UNIQUE,
        email          TEXT    NOT NULL UNIQUE,
        password_hash  TEXT    NOT NULL,
        role           TEXT    NOT NULL CHECK(role IN ('student', 'teacher', 'admin')),
        first_name     TEXT    NOT NULL,
        last_name      TEXT    NOT NULL,
        grad_year      INTEGER,
        department     TEXT,
        account_status TEXT    NOT NULL DEFAULT 'active'
                                CHECK(account_status IN ('active','inactive','suspended')),
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ARTWORKS table
    CREATE TABLE IF NOT EXISTS artworks (
        artwork_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id   INTEGER NOT NULL,
        title        TEXT    NOT NULL,
        description  TEXT,
        file_path    TEXT    NOT NULL,
        upload_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        medium       TEXT    NOT NULL,
        grade        REAL,
        is_public    BOOLEAN DEFAULT 0,
        FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE,
        CHECK (grade IS NULL OR (grade >= 0 AND grade <= 100))
    );

    -- COMMENTS table
    CREATE TABLE IF NOT EXISTS comments (
        comment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        artwork_id   INTEGER NOT NULL,
        teacher_id   INTEGER NOT NULL,
        comment_text TEXT    NOT NULL,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES users(user_id) ON DELETE CASCADE
    );

    -- PORTFOLIOS table
    CREATE TABLE IF NOT EXISTS portfolios (
        portfolio_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id    INTEGER NOT NULL,
        title         TEXT    NOT NULL,
        description   TEXT,
        created_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date  TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE
    );

    -- PORTFOLIO_ARTWORKS table
    CREATE TABLE IF NOT EXISTS portfolio_artworks (
        portfolio_id  INTEGER NOT NULL,
        artwork_id    INTEGER NOT NULL,
        display_order INTEGER DEFAULT 0,
        PRIMARY KEY (portfolio_id, artwork_id),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
        FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE
    );

    -- PDF_EXPORTS table
    CREATE TABLE IF NOT EXISTS pdf_exports (
        pdf_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_id   INTEGER NOT NULL,
        file_name      TEXT    NOT NULL,
        file_path      TEXT    NOT NULL,
        generated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
    );

    -- AUDIT_LOG table
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        action_type TEXT NOT NULL,
        action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        details     TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_artworks_student   ON artworks(student_id);
    CREATE INDEX IF NOT EXISTS idx_comments_artwork   ON comments(artwork_id);
    CREATE INDEX IF NOT EXISTS idx_portfolios_student ON portfolios(student_id);
    CREATE INDEX IF NOT EXISTS idx_audit_user         ON audit_log(user_id);
''')

# ---------------------------------------------------------------------------
# Insert Test Users
# ---------------------------------------------------------------------------

existing_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]

if existing_users == 0:
    cursor.execute("""
        INSERT INTO users
            (username, email, password_hash, role, first_name, last_name, grad_year, department)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "student1",
        "student1@school.edu",
        generate_password_hash("Password123"),
        "student",
        "Student",
        "One",
        2026,
        None
    ))

    cursor.execute("""
        INSERT INTO users
            (username, email, password_hash, role, first_name, last_name, grad_year, department)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "teacher1",
        "teacher1@school.edu",
        generate_password_hash("Password123"),
        "teacher",
        "Teacher",
        "One",
        None,
        "Art"
    ))

    cursor.execute("""
        INSERT INTO users
            (username, email, password_hash, role, first_name, last_name, grad_year, department)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "admin1",
        "admin1@school.edu",
        generate_password_hash("Password123"),
        "admin",
        "Admin",
        "One",
        None,
        "Administration"
    ))

    print("Test users created.")
else:
    print("Users already exist. Skipping test user creation.")

# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

conn.commit()
conn.close()

print("Database created successfully!")