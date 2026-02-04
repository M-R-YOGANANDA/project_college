from extensions import db

class StaffAllocation(db.Model):
    __tablename__ = "staff_allocations"

    allocation_id = db.Column(db.Integer, primary_key=True)

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    class_id = db.Column(
        db.Integer,
        db.ForeignKey("classes.class_id"),
        nullable=False
    )

    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("batches.batch_id"),
        nullable=True
    )

    subject_name = db.Column(db.String(100))
    allocated_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<StaffAllocation staff={self.staff_id}>"
