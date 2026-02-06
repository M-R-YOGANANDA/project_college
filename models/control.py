from extensions import db


class Control(db.Model):
    __tablename__ = "controls"

    control_id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
        nullable=False
    )
    control_type = db.Column(db.String(20), nullable=False)  # attendance | cie
    semester = db.Column(db.Integer, nullable=True)
    month = db.Column(db.String(2), nullable=True)
    cie_type = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    def __repr__(self):
        return f"<Control {self.control_type} branch={self.branch_id} active={self.is_active}>"
