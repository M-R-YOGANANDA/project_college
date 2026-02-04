from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user

def role_required(required_role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Check if user is logged in
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            # 2. Check if user has the correct role
            # We access the role name via the relationship: current_user.role.role_name
            # This assumes your User model implies: 1=admin, 2=hod, 3=staff
            
            # Map role names to IDs if you don't have a direct relationship setup yet
            role_map = {
                "admin": 1,
                "hod": 2,
                "staff": 3
            }
            
            # Get the ID required for this route
            required_id = role_map.get(required_role)

            if current_user.role_id != required_id:
                # If they are logged in but have the wrong role
                return "Access Denied: You do not have the required role.", 403

            return func(*args, **kwargs)
        return wrapper
    return decorator