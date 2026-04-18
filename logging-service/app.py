import json
import os
import time

from flask import Flask, request, jsonify
import hazelcast

app = Flask(__name__)

INSTANCE_NAME = os.getenv("INSTANCE_NAME", "logging-service")
HAZELCAST_MEMBERS = os.getenv(
    "HAZELCAST_MEMBERS",
    "hazelcast-1:5701,hazelcast-2:5701,hazelcast-3:5701"
).split(",")

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=HAZELCAST_MEMBERS
)

transactions_map = hazelcast_client.get_map("transactions").blocking()


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

    app.logger.info(f"[{INSTANCE_NAME}] Received POST: id={tx_id} user={data['user_id']} amount={data['amount']}")
    transactions_map.put(tx_id, value)
    app.logger.info(f"[{INSTANCE_NAME}] Saved to Hazelcast")

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