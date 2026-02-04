from extensions import db

class Branch(db.Model):
    __tablename__ = "branches"

    branch_id = db.Column(db.Integer, primary_key=True)
    branch_code = db.Column(db.String(10), unique=True, nullable=False)
    branch_name = db.Column(db.String(100), nullable=False)

    users = db.relationship("User", backref="branch", lazy=True)
    students = db.relationship("Student", backref="branch", lazy=True)
    classes = db.relationship("Class", backref="branch", lazy=True)

    def __repr__(self):
        return f"<Branch {self.branch_code}>"
