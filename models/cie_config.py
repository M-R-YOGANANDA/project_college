from extensions import db

class CIEConfig(db.Model):
    __tablename__ = "cie_config"

    cie_id = db.Column(db.Integer, primary_key=True)

    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.branch_id"),
        nullable=False
    )

    cie_number = db.Column(db.Integer, nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)

    cie_marks = db.relationship("CIEMarks", backref="cie", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("branch_id", "cie_number", name="unique_branch_cie"),
    )

    def __repr__(self):
        return f"<CIEConfig CIE-{self.cie_number}>"
