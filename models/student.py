from extensions import db

class Student(db.Model):
    __tablename__ = "students"

    student_id = db.Column(db.Integer, primary_key=True)
    register_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
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

    is_active = db.Column(db.Boolean, default=True)

    attendance_records = db.relationship("Attendance", backref="student", lazy=True)
    cie_marks = db.relationship("CIEMarks", backref="student", lazy=True)

    def __repr__(self):
        return f"<Student {self.register_no}>"
