import sqlite3
import hashlib
from datetime import datetime


class User:
    """
    User class representing a user in the system.
    Can be either a student or teacher (determined by role field).
    
    Attributes (from UML diagram):
        user_id: int - Primary key from database
        username: string - Unique username for login
        email: string - User's email address
        password: string - Hashed password (NOT plain text!)
        first_name: string - User's first name
        last_name: string - User's last name
        created_at: date - When account was created
    """
    
    def __init__(self, username, email, password, first_name, last_name, 
                 role, grad_year=None, department=None, user_id=None, created_at=None):
        """
        Create a new User object.
        
        Args:
            username (str): Username for login
            email (str): Email address
            password (str): Plain text password (will be hashed automatically)
            first_name (str): First name
            last_name (str): Last name
            role (str): 'student' or 'teacher'
            grad_year (int, optional): Graduation year (students only)
            department (str, optional): Department (teachers only)
            user_id (int, optional): Database ID (set when loading from DB)
            created_at (str, optional): Creation timestamp (set when loading from DB)
        
        Note: This creates a User object in memory. 
              Call save() to actually store it in the database!
        """
        self.user_id = user_id
        self.username = username
        self.email = email
        # Store password as hash for security
        self.password = self._hash_password(password) if not self._is_already_hashed(password) else password
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.grad_year = grad_year
        self.department = department
        self.created_at = created_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    
    # ========================================================================
    # PRIVATE HELPER METHODS (start with underscore)
    # ========================================================================
    
    def _hash_password(self, password):
        """
        Hash a password using SHA-256.
        This is a PRIVATE method (notice the underscore _).
        
        Args:
            password (str): Plain text password
        
        Returns:
            str: Hashed password
        """
        return hashlib.sha256(password.encode()).hexdigest()
    
    
    def _is_already_hashed(self, password):
        """
        Check if password is already hashed (64 character hex string).
        This prevents double-hashing when loading from database.
        
        Args:
            password (str): Password to check
        
        Returns:
            bool: True if already hashed, False if plain text
        """
        return len(password) == 64 and all(c in '0123456789abcdef' for c in password.lower())
    
    
    def _get_db_connection(self):
        """
        Get a database connection.
        Private method used internally.
        
        Returns:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect('portfolio.db')
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn
    
    
    # ========================================================================
    # PUBLIC METHODS (from UML diagram)
    # ========================================================================
    
    def login(self, password):
        """
        Verify if the provided password is correct.
        
        Args:
            password (str): Plain text password to check
        
        Returns:
            bool: True if password is correct, False otherwise
        
        Example:
            user = User.load_by_username("jsmith")
            if user.login("mypassword"):
                print("Login successful!")
            else:
                print("Wrong password!")
        """
        password_hash = self._hash_password(password)
        return self.password == password_hash
    
    
    def logout(self):
        """
        Logout the user.
        For now, this just prints a message.
        Later with Flask, this would clear the session.
        
        Returns:
            None
        """
        print(f"{self.username} has been logged out.")
    
    
    def update_profile(self, **kwargs):
        """
        Update user profile information.
        
        Args:
            **kwargs: Any attributes to update (first_name, last_name, email, etc.)
        
        Returns:
            bool: True if successful, False otherwise
        
        Example:
            user.update_profile(email="newemail@school.edu", first_name="Johnny")
        """
        # Update object attributes
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Save changes to database
        return self.save()
    
    
    # ========================================================================
    # DATABASE METHODS (Save/Load)
    # ========================================================================
    
    def save(self):
        """
        Save this user to the database.
        Creates a NEW user if user_id is None.
        Updates EXISTING user if user_id is set.
        
        Returns:
            bool: True if successful, False otherwise
        
        Example:
            # Create new user
            user = User("jsmith", "john@school.edu", "password123", 
                       "John", "Smith", "student", grad_year=2025)
            user.save()  # Saves to database
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            if self.user_id is None:
                # INSERT - creating new user
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, role, 
                                     first_name, last_name, grad_year, department, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (self.username, self.email, self.password, self.role,
                      self.first_name, self.last_name, self.grad_year, 
                      self.department, self.created_at))
                
                # Get the auto-generated user_id
                self.user_id = cursor.lastrowid
            else:
                # UPDATE - modifying existing user
                cursor.execute('''
                    UPDATE users 
                    SET username=?, email=?, password_hash=?, role=?,
                        first_name=?, last_name=?, grad_year=?, department=?
                    WHERE user_id=?
                ''', (self.username, self.email, self.password, self.role,
                      self.first_name, self.last_name, self.grad_year,
                      self.department, self.user_id))
            
            conn.commit()
            conn.close()
            return True
            
        except sqlite3.IntegrityError as e:
            # Username or email already exists
            conn.close()
            print(f"Error: {e}")
            return False
        except Exception as e:
            conn.close()
            print(f"Error saving user: {e}")
            return False
    
    
    @staticmethod
    def load_by_username(username):
        """
        Load a user from the database by username.
        This is a STATIC method - call it on the class, not an instance.
        
        Args:
            username (str): Username to look up
        
        Returns:
            User object if found, None if not found
        
        Example:
            user = User.load_by_username("jsmith")
            if user:
                print(f"Found: {user.first_name}")
            else:
                print("User not found")
        """
        conn = sqlite3.connect('portfolio.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        # Create User object from database row
        return User(
            username=row['username'],
            email=row['email'],
            password=row['password_hash'],  # Already hashed
            first_name=row['first_name'],
            last_name=row['last_name'],
            role=row['role'],
            grad_year=row['grad_year'],
            department=row['department'],
            user_id=row['user_id'],
            created_at=row['created_at']
        )
    
    
    @staticmethod
    def load_by_id(user_id):
        """
        Load a user from the database by user_id.
        
        Args:
            user_id (int): User ID to look up
        
        Returns:
            User object if found, None if not found
        """
        conn = sqlite3.connect('portfolio.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        return User(
            username=row['username'],
            email=row['email'],
            password=row['password_hash'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            role=row['role'],
            grad_year=row['grad_year'],
            department=row['department'],
            user_id=row['user_id'],
            created_at=row['created_at']
        )
    
    
    # ========================================================================
    # SPECIAL METHODS (Python magic methods)
    # ========================================================================
    
    def __str__(self):
        """
        String representation of User.
        
        Returns:
            str: User description
        """
        return f"User({self.username}, {self.first_name} {self.last_name}, {self.role})"
    
    
    def __repr__(self):
        """
        Developer-friendly representation.
        Used when you type the object name in Python console.
        
        Returns:
            str: Detailed representation
        """
        return f"User(id={self.user_id}, username='{self.username}', role='{self.role}')"