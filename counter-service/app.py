import json
import os
import time
import threading
import requests
import hazelcast

from flask import Flask, jsonify
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from models import db, Account, Transaction

app = Flask(__name__)

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "bankdb")

SERVICE_NAME = "counter-service"
SERVICE_HOST = os.getenv("SERVICE_HOST", "counter-service")
SERVICE_PORT = os.getenv("SERVICE_PORT", "5002")
CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://config-server:5005")

HAZELCAST_MEMBERS = os.getenv(
    "HAZELCAST_MEMBERS",
    "hazelcast-1:5701,hazelcast-2:5701,hazelcast-3:5701"
).split(",")

QUEUE_NAME = os.getenv("QUEUE_NAME", "counter-queue")

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


def register_in_config_server():
    address = f"http://{SERVICE_HOST}:{SERVICE_PORT}"
    payload = {
        "service_name": SERVICE_NAME,
        "address": address
    }

    for attempt in range(30):
        try:
            response = requests.post(f"{CONFIG_SERVER_URL}/register", json=payload, timeout=5)
            if response.status_code == 200:
                print(f"[counter-service] Registered in config-server: {address}")
                return
        except Exception as e:
            print(f"[counter-service] Registration failed, retrying... {e}")
            time.sleep(2)

    raise RuntimeError("[counter-service] Could not register in config-server")


with app.app_context():
    wait_for_db()
    db.create_all()

register_in_config_server()

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=HAZELCAST_MEMBERS
)
counter_queue = hazelcast_client.get_queue(QUEUE_NAME).blocking()


def apply_transaction_to_db(data):
    tx_id = str(data["transaction_id"])
    user_id = str(data["user_id"])
    amount = int(data["amount"])
    timestamp = float(data["timestamp"])

    existing_tx = Transaction.query.filter_by(transaction_id=tx_id).first()
    if existing_tx is not None:
        return

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


def consumer_loop():
    print("[counter-service] Consumer thread started")
    while True:
        try:
            item = counter_queue.take()
            data = json.loads(item)

            with app.app_context():
                apply_transaction_to_db(data)

            print(f"[counter-service] Applied transaction {data['transaction_id']} for user {data['user_id']}")
        except Exception as e:
            print(f"[counter-service] Consumer error: {e}")
            time.sleep(1)


consumer_thread = threading.Thread(target=consumer_loop, daemon=True)
consumer_thread.start()


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