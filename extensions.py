from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager  # <--- NEW IMPORT

db = SQLAlchemy()
login_manager = LoginManager()        # <--- NEW LINE