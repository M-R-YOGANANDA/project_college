from extensions import db

class Class(db.Model):
    __tablename__ = "classes"

    class_id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
        nullable=False
    )
    class_name = db.Column(db.String(20), nullable=False)
    academic_year = db.Column(db.String(9), nullable=False)

    batches = db.relationship("Batch", backref="class_", lazy=True)
    students = db.relationship("Student", backref="class_", lazy=True)

    def __repr__(self):
        return f"<Class {self.class_name}>"
