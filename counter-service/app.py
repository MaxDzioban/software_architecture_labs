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

HAZELCAST_SERVICE = os.getenv("HAZELCAST_SERVICE", "hazelcast")
HAZELCAST_PORT = int(os.getenv("HAZELCAST_PORT", "5701"))
QUEUE_NAME = os.getenv("QUEUE_NAME", "counter-queue")

KUBE_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
KUBE_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
KUBE_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBE_SERVICE_HOST = os.getenv("KUBERNETES_SERVICE_HOST")
KUBE_SERVICE_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


def running_in_cluster():
    return bool(KUBE_SERVICE_HOST and os.path.exists(KUBE_TOKEN_PATH))


def read_kubernetes_namespace():
    if os.path.exists(KUBE_NAMESPACE_PATH):
        with open(KUBE_NAMESPACE_PATH, "r") as stream:
            return stream.read().strip()
    return "default"


def get_kubernetes_api_headers():
    with open(KUBE_TOKEN_PATH, "r") as stream:
        token = stream.read().strip()
    return {"Authorization": f"Bearer {token}"}


def get_kubernetes_endpoints(service_name: str):
    if not running_in_cluster():
        return []

    namespace = read_kubernetes_namespace()
    url = (
        f"https://{KUBE_SERVICE_HOST}:{KUBE_SERVICE_PORT}"
        f"/api/v1/namespaces/{namespace}/endpoints/{service_name}"
    )

    try:
        response = requests.get(
            url,
            headers=get_kubernetes_api_headers(),
            verify=KUBE_CA_PATH,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    members = []
    for subset in data.get("subsets", []):
        ports = subset.get("ports", [])
        addresses = subset.get("addresses", [])
        for address in addresses:
            for port in ports:
                members.append(f"{address['ip']}:{port['port']}")

    return members


def get_hazelcast_members():
    members = get_kubernetes_endpoints(HAZELCAST_SERVICE)
    if members:
        return members
    return [f"{HAZELCAST_SERVICE}:{HAZELCAST_PORT}"]

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=get_hazelcast_members()
)

counter_queue = hazelcast_client.get_queue(QUEUE_NAME).blocking()


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
            print(
                f"[counter-service] Database not ready yet "
                f"(attempt {attempt}/{max_retries}): {e}"
            )
            time.sleep(delay)

    raise RuntimeError("Database did not become ready in time")


with app.app_context():
    wait_for_db()
    db.create_all()


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
            print(
                f"[counter-service] Applied transaction "
                f"{data['transaction_id']} for user {data['user_id']}"
            )
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