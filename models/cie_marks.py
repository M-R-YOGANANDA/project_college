from extensions import db

class CIEMarks(db.Model):
    __tablename__ = "cie_marks"

    cie_mark_id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.student_id"),
        nullable=False
    )

    cie_id = db.Column(
        db.Integer,
        db.ForeignKey("cie_config.cie_id"),
        nullable=False
    )

    marks_obtained = db.Column(db.Integer, nullable=False)

    entered_by = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("student_id", "cie_id", name="unique_student_cie"),
    )

    def __repr__(self):
        return f"<CIEMarks student={self.student_id}>"
