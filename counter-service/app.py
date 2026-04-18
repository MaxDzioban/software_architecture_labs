import os
import time

from flask import Flask, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from models import db, Account, Transaction

app = Flask(__name__)

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "bankdb")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


def wait_for_db(max_retries=30, delay=2):
    for attempt in range(1, max_retries + 1):
        try:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                db.session.commit()
            print(f"[counter-service] Database is ready on attempt {attempt}")
            return
        except OperationalError as e:
            print(f"[counter-service] Database not ready yet (attempt {attempt}/{max_retries}): {e}")
            time.sleep(delay)

    raise RuntimeError("Database did not become ready in time")


with app.app_context():
    wait_for_db()
    db.create_all()

@app.route("/apply", methods=["POST"])
def apply_transaction():
    data = request.get_json(force=True, silent=False)

    required = ["transaction_id", "user_id", "amount", "timestamp"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"missing field: {field}"}), 400

    tx_id = str(data["transaction_id"])
    user_id = str(data["user_id"])
    amount = int(data["amount"])
    timestamp = float(data["timestamp"])

    try:
        existing_tx = Transaction.query.filter_by(transaction_id=tx_id).first()
        if existing_tx is not None:
            account = Account.query.filter_by(user_id=user_id).first()
            balance = account.balance if account else 0
            return jsonify({
                "transaction_id": tx_id,
                "user_id": user_id,
                "balance": balance,
                "status": "already_applied"
            }), 200

        tx = Transaction(
            transaction_id=tx_id,
            user_id=user_id,
            amount=amount,
            timestamp=timestamp
        )
        db.session.add(tx)
        db.session.flush()

        account = Account.query.filter_by(user_id=user_id).first()
        if account is None:
            account = Account(user_id=user_id, balance=0)
            db.session.add(account)
            db.session.flush()

        Account.query.filter_by(user_id=user_id).update({
            Account.balance: Account.balance + amount
        })

        db.session.commit()

        updated_account = Account.query.filter_by(user_id=user_id).first()

        return jsonify({
            "transaction_id": tx_id,
            "user_id": user_id,
            "balance": updated_account.balance
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "apply failed", "details": str(e)}), 500


@app.route("/balance/<user_id>", methods=["GET"])
def get_balance(user_id):
    account = Account.query.filter_by(user_id=str(user_id)).first()
    balance = account.balance if account else 0

    return jsonify({
        "user_id": str(user_id),
        "balance": balance
    }), 200


@app.route("/accounts", methods=["GET"])
def get_accounts():
    accounts = Account.query.all()
    balances = {account.user_id: account.balance for account in accounts}
    return jsonify({"balances": balances}), 200


@app.route("/reset", methods=["POST"])
def reset():
    Transaction.query.delete()
    Account.query.delete()
    db.session.commit()
    return jsonify({"status": "reset"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, threaded=True)