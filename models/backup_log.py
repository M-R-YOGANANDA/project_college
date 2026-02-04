from extensions import db

class BackupLog(db.Model):
    __tablename__ = "backup_logs"

    backup_id = db.Column(db.Integer, primary_key=True)
    backup_type = db.Column(db.String(50))
    backup_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<BackupLog {self.backup_id}>"
