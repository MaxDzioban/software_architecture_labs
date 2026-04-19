import json
import os
import time
import requests
import hazelcast

from flask import Flask, request, jsonify

app = Flask(__name__)

INSTANCE_NAME = os.getenv("INSTANCE_NAME", "logging-service")
SERVICE_NAME = "logging-service"
SERVICE_HOST = os.getenv("SERVICE_HOST", "logging-service")
SERVICE_PORT = os.getenv("SERVICE_PORT", "5001")
CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://config-server:5005")

HAZELCAST_MEMBERS = os.getenv(
    "HAZELCAST_MEMBERS",
    "hazelcast-1:5701,hazelcast-2:5701,hazelcast-3:5701"
).split(",")

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=HAZELCAST_MEMBERS
)
transactions_map = hazelcast_client.get_map("transactions").blocking()


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
                print(f"[{INSTANCE_NAME}] Registered in config-server: {address}")
                return
        except Exception as e:
            print(f"[{INSTANCE_NAME}] Registration failed, retrying... {e}")
            time.sleep(2)

    raise RuntimeError(f"[{INSTANCE_NAME}] Could not register in config-server")


register_in_config_server()


@app.route("/log", methods=["POST"])
def log_transaction():
    data = request.get_json(force=True, silent=False)

    required = ["transaction_id", "user_id", "amount", "timestamp"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"missing field: {field}"}), 400

    tx_id = str(data["transaction_id"])
    value = json.dumps({
        "transaction_id": tx_id,
        "user_id": str(data["user_id"]),
        "amount": int(data["amount"]),
        "timestamp": float(data["timestamp"]),
        "logged_by": INSTANCE_NAME
    })

    print(f"[{INSTANCE_NAME}] Received POST: id={tx_id} user={data['user_id']} amount={data['amount']}")
    transactions_map.put(tx_id, value)
    print(f"[{INSTANCE_NAME}] Saved to Hazelcast")

    return jsonify({"status": "ok", "instance": INSTANCE_NAME}), 200


@app.route("/transactions", methods=["GET"])
def get_all_transactions():
    entries = transactions_map.entry_set()
    transactions = [json.loads(value) for _, value in entries]
    return jsonify({
        "instance": INSTANCE_NAME,
        "transactions": transactions
    }), 200


@app.route("/transactions/<user_id>", methods=["GET"])
def get_transactions_by_user(user_id):
    entries = transactions_map.entry_set()
    transactions = []

    for _, value in entries:
        item = json.loads(value)
        if str(item["user_id"]) == str(user_id):
            transactions.append(item)

    return jsonify({
        "instance": INSTANCE_NAME,
        "user_id": str(user_id),
        "transactions": transactions
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "instance": INSTANCE_NAME,
        "time": time.time()
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)