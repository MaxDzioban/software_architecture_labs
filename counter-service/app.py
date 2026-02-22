from flask import Flask, request, jsonify
from threading import Lock

app = Flask(__name__)

BAL = {}
lock = Lock()

@app.post("/apply")
def apply_tx():
    data = request.get_json(force=True, silent=False)
    required = ["user_id", "amount"]
    for k in required:
        if k not in data:
            return jsonify({"error": f"missing field: {k}"}), 400
    uid = str(data["user_id"])
    amount = int(data["amount"])
    with lock:
        BAL[uid] = BAL.get(uid, 0) + amount
        new_balance = BAL[uid]
    return jsonify({"user_id": uid, "balance": new_balance}), 200



@app.get("/balance/<user_id>")
def get_balance(user_id):
    uid = str(user_id)
    with lock:
        bal = BAL.get(uid, 0)
    return jsonify({"user_id": uid, "balance": bal}), 200

@app.get("/accounts")
def get_all_accounts():
    with lock:
        return jsonify({"balances": BAL}), 200

@app.post("/reset")
def reset():
    with lock:
        BAL.clear()
    return jsonify({"status": "reset"}), 200

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
