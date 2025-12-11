"""
Migration script for User model enhancements.

Run this script to add new columns to the User table:
- email
- created_at
- last_login
- is_active

Usage:
    python scripts/migrate_user_model.py
    
Note: This is a safe migration that adds columns with default values.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from sqlalchemy import text


def migrate_user_table():
    """Add new columns to the user table."""
    app = create_app()
    
    with app.app_context():
        connection = db.engine.connect()
        
        # Get existing columns
        result = connection.execute(text("PRAGMA table_info(user)"))
        existing_columns = {row[1] for row in result.fetchall()}
        
        print(f"Existing columns: {existing_columns}")
        
        migrations = []
        
        # Add email column
        if 'email' not in existing_columns:
            migrations.append(
                "ALTER TABLE user ADD COLUMN email VARCHAR(120)"
            )
            print("  + Adding 'email' column")
        
        # Add created_at column
        if 'created_at' not in existing_columns:
            migrations.append(
                "ALTER TABLE user ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            )
            print("  + Adding 'created_at' column")
        
        # Add last_login column
        if 'last_login' not in existing_columns:
            migrations.append(
                "ALTER TABLE user ADD COLUMN last_login DATETIME"
            )
            print("  + Adding 'last_login' column")
        
        # Add is_active column
        if 'is_active' not in existing_columns:
            migrations.append(
                "ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1"
            )
            print("  + Adding 'is_active' column")
        
        if not migrations:
            print("\n✓ User table is already up to date!")
            return
        
        # Execute migrations
        print(f"\nRunning {len(migrations)} migration(s)...")
        
        for sql in migrations:
            try:
                connection.execute(text(sql))
                connection.commit()
            except Exception as e:
                print(f"  Warning: {e}")
        
        print("\n✓ Migration completed successfully!")
        
        # Verify
        result = connection.execute(text("PRAGMA table_info(user)"))
        final_columns = {row[1] for row in result.fetchall()}
        print(f"Final columns: {final_columns}")
        
        connection.close()


if __name__ == '__main__':
    print("="*50)
    print("User Model Migration")
    print("="*50)
    migrate_user_table()
