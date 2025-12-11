"""
Logging configuration for SAT Application.

Provides structured logging with different handlers for development and production.
"""

import logging
import logging.handlers
import os
from datetime import datetime


def setup_logging(app):
    """
    Configure logging for the Flask application.
    
    Args:
        app: Flask application instance
    """
    # Get log level from config or environment
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Create logs directory if not exists
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # Console handler (always active)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler for general logs (rotating)
    if not app.config.get('TESTING', False):
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(logs_dir, 'sat_app.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)
        
        # Separate error log file
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(logs_dir, 'errors.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        root_logger.addHandler(error_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    app.logger.info(f"Logging configured: level={log_level}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)


class AuditLogger:
    """
    Audit logger for tracking important user actions.
    
    Usage:
        audit = AuditLogger()
        audit.log_action('user_login', user_id=1, username='admin')
    """
    
    def __init__(self):
        self.logger = logging.getLogger('audit')
        self.logger.setLevel(logging.INFO)
    
    def log_action(self, action: str, user_id: int = None, **kwargs):
        """
        Log an auditable action.
        
        Args:
            action: Action identifier (e.g., 'user_login', 'company_created')
            user_id: ID of the user performing the action
            **kwargs: Additional context to log
        """
        context = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'user_id': user_id,
            **kwargs
        }
        self.logger.info(f"AUDIT: {context}")
    
    def log_login(self, user_id: int, username: str, success: bool, ip_address: str = None):
        """Log a login attempt."""
        self.log_action(
            'login_attempt',
            user_id=user_id,
            username=username,
            success=success,
            ip_address=ip_address
        )
    
    def log_data_change(self, model: str, record_id: int, action: str, user_id: int, changes: dict = None):
        """Log a data modification."""
        self.log_action(
            'data_change',
            user_id=user_id,
            model=model,
            record_id=record_id,
            change_type=action,
            changes=changes
        )


# Global audit logger instance
audit_logger = AuditLogger()
