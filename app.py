from flask import Flask
from config.config import Config
from flask_migrate import Migrate
# 1. NEW IMPORT: Get login_manager from extensions
from extensions import db, login_manager 

# Route Imports
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.hod_routes import hod_bp
from routes.staff_routes import staff_bp

# Model Imports (kept as you had them)
from models.user import User
from models.class_model import Class
from models.batch import Batch
from models.student import Student
from models.staff_allocation import StaffAllocation
from models.attendance import Attendance
from models.cie_config import CIEConfig
from models.cie_marks import CIEMarks
from models.cie_papers import CIEPapers
from models.backup_log import BackupLog
from models.role import Role
from models.branch import Branch

migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 2. NEW CODE: Initialize Login Manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login' # Where to go if not logged in

    # 3. NEW CODE: User Loader Function
    @login_manager.user_loader
    def load_user(user_id):
        # Use db.session.get() instead of User.query.get() to fix the warning
        return db.session.get(User, int(user_id))

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(hod_bp)
    app.register_blueprint(staff_bp)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
