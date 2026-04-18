from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Account(db.Model):
    __tablename__ = "accounts"

    user_id = db.Column(db.String(100), primary_key=True)
    balance = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "balance": self.balance
        }


class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id = db.Column(db.String(100), primary_key=True)
    user_id = db.Column(db.String(100), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "timestamp": self.timestamp
        }