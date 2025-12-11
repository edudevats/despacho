"""
CLI Commands for SAT Application

Usage:
    flask create-admin               # Create admin user interactively
    flask create-admin --password X  # Create admin with specific password
    flask generate-key               # Generate new FERNET encryption key
"""

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash
import secrets
import string


def register_commands(app):
    """Register CLI commands with Flask app."""
    
    @app.cli.command('create-admin')
    @click.option('--username', default='admin', help='Admin username')
    @click.option('--password', default=None, help='Admin password (generated if not provided)')
    @click.option('--force', is_flag=True, help='Overwrite existing admin user')
    @with_appcontext
    def create_admin(username, password, force):
        """Create an admin user for the application."""
        from extensions import db
        from models import User
        
        existing = User.query.filter_by(username=username).first()
        
        if existing and not force:
            click.echo(f"Error: User '{username}' already exists. Use --force to overwrite.")
            return
        
        if existing and force:
            db.session.delete(existing)
            db.session.commit()
            click.echo(f"Deleted existing user '{username}'")
        
        # Generate secure password if not provided
        if not password:
            password = generate_secure_password()
            click.echo(f"\nGenerated secure password: {password}")
            click.echo("⚠️  Save this password now! It won't be shown again.\n")
        
        # Validate password strength
        is_valid, message = validate_password_strength(password)
        if not is_valid:
            click.echo(f"Error: Password too weak - {message}")
            return
        
        user = User(
            username=username,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        click.echo(f"✓ Admin user '{username}' created successfully!")
    
    @app.cli.command('generate-key')
    def generate_encryption_key():
        """Generate a new FERNET encryption key."""
        from cryptography.fernet import Fernet
        
        key = Fernet.generate_key().decode()
        click.echo("\n🔐 New FERNET encryption key generated:\n")
        click.echo(f"FERNET_KEY={key}")
        click.echo("\n⚠️  Add this to your .env file and keep it secure!")
        click.echo("    Losing this key means losing access to encrypted data.\n")
    
    @app.cli.command('check-security')
    @with_appcontext
    def check_security():
        """Check application security configuration."""
        import os
        from models import User
        
        issues = []
        warnings = []
        
        # Check SECRET_KEY
        secret_key = os.environ.get('SECRET_KEY', app.config.get('SECRET_KEY', ''))
        if 'dev' in secret_key.lower() or 'change' in secret_key.lower():
            issues.append("SECRET_KEY appears to be a development/default value")
        
        # Check FERNET_KEY
        if not os.environ.get('FERNET_KEY'):
            if os.path.exists('secret.key'):
                warnings.append("Using legacy secret.key file - consider migrating to FERNET_KEY env var")
            else:
                issues.append("FERNET_KEY not set - encrypted data features will fail")
        
        # Check for default admin user
        admin = User.query.filter_by(username='admin').first()
        if admin:
            warnings.append("Default 'admin' user exists - consider using a unique username")
        
        # Check debug mode
        if app.config.get('DEBUG', False):
            warnings.append("DEBUG mode is enabled - disable in production")
        
        # Print results
        click.echo("\n🔒 Security Check Results\n")
        
        if issues:
            click.echo("❌ CRITICAL ISSUES:")
            for issue in issues:
                click.echo(f"   • {issue}")
            click.echo()
        
        if warnings:
            click.echo("⚠️  WARNINGS:")
            for warning in warnings:
                click.echo(f"   • {warning}")
            click.echo()
        
        if not issues and not warnings:
            click.echo("✓ No security issues detected!")
        elif not issues:
            click.echo("✓ No critical issues, but review warnings above.")
        else:
            click.echo("⚠️  Please address critical issues before deploying to production!")


def generate_secure_password(length: int = 16) -> str:
    """Generate a cryptographically secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each required character type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]
    # Fill remaining length
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    # Shuffle to avoid predictable positions
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """
    Validate password meets security requirements.
    
    Returns:
        tuple: (is_valid, error_message)
    """
    import re
    
    if len(password) < 8:
        return False, "Must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Must contain at least one digit"
    
    return True, None
