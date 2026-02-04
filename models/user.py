from extensions import db
from flask_login import UserMixin  # <--- 1. ADD THIS IMPORT

# <--- 2. ADD UserMixin HERE
class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.role_id"),
        nullable=False
    )

    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
        nullable=False
    )

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # <--- 3. ADD THIS METHOD
    # Flask-Login looks for "id", but your column is "user_id".
    # We must explicitly tell it what the ID is.
    def get_id(self):
        return str(self.user_id)

    def __repr__(self):
        return f"<User {self.username}>"