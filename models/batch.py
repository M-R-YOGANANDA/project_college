from extensions import db

class Batch(db.Model):
    __tablename__ = 'batches'
    batch_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.class_id'), nullable=False)
    batch_name = db.Column(db.String(10), nullable=False)

    def __repr__(self):
        return f'<Batch {self.batch_name}>'