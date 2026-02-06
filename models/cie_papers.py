from extensions import db

class CIEPapers(db.Model):
    __tablename__ = "cie_papers"

    paper_id = db.Column(db.Integer, primary_key=True)

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
        nullable=False
    )

    semester = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())
    subject_code = db.Column(db.String(50), nullable=False)
    is_displayed = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<CIEPaper {self.paper_id}>"
