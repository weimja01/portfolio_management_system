import sqlite3

conn = sqlite3.connect('portfolio.db')
cursor = conn.cursor()

#tables

cursor.executescript('''
    -- USERS table
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        grad_year INTEGER,
        department TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
 
    -- ARTWORKS table
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
        FOREIGN KEY (student_id) REFERENCES users(user_id) ON DELETE CASCADE,
        CHECK (grade IS NULL OR (grade >= 0 AND grade <= 100))
    );
 
    -- COMMENTS table
    CREATE TABLE IF NOT EXISTS comments (
        comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        artwork_id INTEGER NOT NULL,
        teacher_id INTEGER NOT NULL,
        comment_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (artwork_id) REFERENCES artworks(artwork_id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES users(user_id) ON DELETE CASCADE
    );
 
    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_artworks_student ON artworks(student_id);
    CREATE INDEX IF NOT EXISTS idx_comments_artwork ON comments(artwork_id);
''')
 

conn.commit()
conn.close()

print("Database Created!")