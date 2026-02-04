from extensions import db

class Attendance(db.Model):
    __tablename__ = "attendance"

    attendance_id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.student_id"),
        nullable=False
    )

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum("PRESENT", "ABSENT"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("student_id", "date", name="unique_student_date"),
    )

    def __repr__(self):
        return f"<Attendance student={self.student_id} {self.date}>"
