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

    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("subjects.subject_id"),
        nullable=False
    )

    total_classes = db.Column(db.Integer, nullable=False, default=0)
    classes_attended = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", name="unique_student_subject"),
    )

    def __repr__(self):
        return f"<Attendance student={self.student_id} subject={self.subject_id}>"
