from extensions import db
# In models.py (Add this new class)
class MaintenanceMode(db.Model):
    __tablename__ = 'maintenance_mode'
    id = db.Column(db.Integer, primary_key=True)
    is_maintenance = db.Column(db.Boolean, default=False)