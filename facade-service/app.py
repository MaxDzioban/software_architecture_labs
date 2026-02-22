import time
import uuid
from flask import Flask, request, jsonify
import requests
from threading import Lock

app = Flask(__name__)

LOGGING_URL = "http://logging-service:5001"
COUNTER_URL = "http://counter-service:5002"

stats_lock = Lock()
stats = {
    "logging_calls": 0,
    "logging_time_sec": 0.0,
    "counter_calls": 0,
    "counter_time_sec": 0.0,
}

def _timed_request(method, url, **kwargs):
    start = time.perf_counter()
    resp = requests.request(method, url, timeout=5, **kwargs)
    elapsed = time.perf_counter() - start
    return resp, elapsed

def _add_stat(which: str, elapsed: float):
    with stats_lock:
        stats[f"{which}_calls"] += 1
        stats[f"{which}_time_sec"] += elapsed

@app.post("/transaction")
def post_transaction():
    data = request.get_json(force=True, silent=False)
    if "user_id" not in data or "amount" not in data:
        return jsonify({"error": "required: {user_id, amount}"}), 400

    user_id = str(data["user_id"])
    amount = int(data["amount"])

    ts = time.time()
    tx_id = str(uuid.uuid4())

    tx = {
        "transaction_id": tx_id,
        "user_id": user_id,
        "amount": amount,
        "timestamp": ts,
    }

    log_resp, log_t = _timed_request("POST", f"{LOGGING_URL}/log", json=tx)
    _add_stat("logging", log_t)
    if log_resp.status_code != 200:
        return jsonify({"error": "logging-service failed", "details": log_resp.text}), 502
    cnt_resp, cnt_t = _timed_request("POST", f"{COUNTER_URL}/apply", json={"user_id": user_id, "amount": amount})
    _add_stat("counter", cnt_t)
    if cnt_resp.status_code != 200:
        return jsonify({"error": "counter-service failed", "details": cnt_resp.text}), 502
    balance = cnt_resp.json().get("balance", 0)
    return jsonify({"transaction_id": tx_id, "balance": balance}), 200



@app.get("/user/<user_id>")
def get_user(user_id):
    uid = str(user_id)
    bal_resp, cnt_t = _timed_request("GET", f"{COUNTER_URL}/balance/{uid}")
    _add_stat("counter", cnt_t)
    if bal_resp.status_code != 200:
        return jsonify({"error": "counter-service failed", "details": bal_resp.text}), 502
    balance = bal_resp.json().get("balance", 0)
    tx_resp, log_t = _timed_request("GET", f"{LOGGING_URL}/transactions/{uid}")
    _add_stat("logging", log_t)
    if tx_resp.status_code != 200:
        return jsonify({"error": "logging-service failed", "details": tx_resp.text}), 502
    transactions = tx_resp.json().get("transactions", [])

    return jsonify({"user_id": uid, "balance": balance, "transactions": transactions}), 200


@app.get("/accounts")
def get_accounts():
    resp, cnt_t = _timed_request("GET", f"{COUNTER_URL}/accounts")
    _add_stat("counter", cnt_t)
    if resp.status_code != 200:
        return jsonify({"error": "counter-service failed", "details": resp.text}), 502
    return jsonify(resp.json()), 200

@app.get("/stats")
def get_stats():
    with stats_lock:
        s = dict(stats)
    s["logging_avg_ms"] = (s["logging_time_sec"] / s["logging_calls"] * 1000) if s["logging_calls"] else 0.0
    s["counter_avg_ms"] = (s["counter_time_sec"] / s["counter_calls"] * 1000) if s["counter_calls"] else 0.0
    return jsonify(s), 200

@app.post("/stats/reset")
def reset_stats():
    with stats_lock:
        stats["logging_calls"] = 0
        stats["logging_time_sec"] = 0.0
        stats["counter_calls"] = 0
        stats["counter_time_sec"] = 0.0
    return jsonify({"status": "reset"}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
