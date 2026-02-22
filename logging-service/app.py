from flask import Flask, request, jsonify
from threading import Lock
app = Flask(__name__)

TX = {}
lock = Lock()

@app.post("/log")
def log_tx():
    data = request.get_json(force=True, silent=False)
    required = ["transaction_id", "user_id", "amount", "timestamp"]
    for k in required:
        if k not in data:
            return jsonify({"error": f"missing field: {k}"}), 400

    tx_id = str(data["transaction_id"])
    with lock:
        TX[tx_id] = {
            "transaction_id": tx_id,
            "user_id": str(data["user_id"]),
            "amount": int(data["amount"]),
            "timestamp": data["timestamp"],
        }
    app.logger.info(f"LOGGED: {TX[tx_id]}")
    return jsonify({"status": "ok"}), 200



@app.get("/transactions")
def get_all():
    with lock:
        return jsonify({"transactions": list(TX.values())}), 200



@app.get("/transactions/<user_id>")
def get_by_user(user_id):
    uid = str(user_id)
    with lock:
        user_txs = [t for t in TX.values() if t["user_id"] == uid]
    return jsonify({"user_id": uid, "transactions": user_txs}), 200



@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
