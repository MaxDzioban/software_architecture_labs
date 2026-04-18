import os
import time
import uuid
import random
from threading import Lock

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

COUNTER_URL = os.getenv("COUNTER_URL", "http://counter-service:5002")

LOGGING_ENDPOINTS = [
    os.getenv("LOGGING_URL_1", "http://logging-service-1:5001"),
    os.getenv("LOGGING_URL_2", "http://logging-service-2:5001"),
    os.getenv("LOGGING_URL_3", "http://logging-service-3:5001"),
]

stats_lock = Lock()
stats = {
    "logging_calls": 0,
    "logging_time_sec": 0.0,
    "counter_calls": 0,
    "counter_time_sec": 0.0,
}


def add_stat(service_name: str, elapsed: float):
    with stats_lock:
        stats[f"{service_name}_calls"] += 1
        stats[f"{service_name}_time_sec"] += elapsed


def timed_request(method: str, url: str, **kwargs):
    start = time.perf_counter()
    response = requests.request(method, url, timeout=20, **kwargs)
    elapsed = time.perf_counter() - start
    return response, elapsed


def call_counter(method: str, path: str, **kwargs):
    url = f"{COUNTER_URL}{path}"
    response, elapsed = timed_request(method, url, **kwargs)
    add_stat("counter", elapsed)
    return response


def call_logging_with_retry(method: str, path: str, **kwargs):
    endpoints = LOGGING_ENDPOINTS[:]
    random.shuffle(endpoints)

    last_error = None

    for base_url in endpoints:
        try:
            url = f"{base_url}{path}"
            response, elapsed = timed_request(method, url, **kwargs)
            add_stat("logging", elapsed)

            if response.status_code < 500:
                return response
        except Exception as e:
            last_error = e

    if last_error:
        raise last_error

    raise RuntimeError("All logging-service instances failed")


@app.route("/transaction", methods=["POST"])
def create_transaction():
    data = request.get_json(force=True, silent=False)

    if "user_id" not in data or "amount" not in data:
        return jsonify({"error": "required fields: user_id, amount"}), 400

    transaction = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(data["user_id"]),
        "amount": int(data["amount"]),
        "timestamp": time.time()
    }

    try:
        counter_resp = call_counter("POST", "/apply", json=transaction)
    except Exception as e:
        return jsonify({"error": "counter-service unavailable", "details": str(e)}), 502

    if counter_resp.status_code != 200:
        return jsonify({
            "error": "counter-service failed",
            "details": counter_resp.text
        }), 502

    try:
        logging_resp = call_logging_with_retry("POST", "/log", json=transaction)
    except Exception as e:
        return jsonify({"error": "all logging-service instances unavailable", "details": str(e)}), 502

    if logging_resp.status_code != 200:
        return jsonify({
            "error": "logging-service failed",
            "details": logging_resp.text
        }), 502

    balance = counter_resp.json().get("balance", 0)
    return jsonify({
        "transaction_id": transaction["transaction_id"],
        "balance": balance
    }), 200


@app.route("/user/<user_id>", methods=["GET"])
def get_user_info(user_id):
    try:
        counter_resp = call_counter("GET", f"/balance/{user_id}")
    except Exception as e:
        return jsonify({"error": "counter-service unavailable", "details": str(e)}), 502

    if counter_resp.status_code != 200:
        return jsonify({
            "error": "counter-service failed",
            "details": counter_resp.text
        }), 502

    try:
        logging_resp = call_logging_with_retry("GET", f"/transactions/{user_id}")
    except Exception as e:
        return jsonify({"error": "all logging-service instances unavailable", "details": str(e)}), 502

    if logging_resp.status_code != 200:
        return jsonify({
            "error": "logging-service failed",
            "details": logging_resp.text
        }), 502

    return jsonify({
        "user_id": str(user_id),
        "balance": counter_resp.json().get("balance", 0),
        "transactions": logging_resp.json().get("transactions", [])
    }), 200


@app.route("/accounts", methods=["GET"])
def get_accounts():
    try:
        response = call_counter("GET", "/accounts")
    except Exception as e:
        return jsonify({"error": "counter-service unavailable", "details": str(e)}), 502

    if response.status_code != 200:
        return jsonify({"error": "counter-service failed", "details": response.text}), 502

    return jsonify(response.json()), 200


@app.route("/stats", methods=["GET"])
def get_stats():
    with stats_lock:
        result = dict(stats)

    result["logging_avg_ms"] = (
        result["logging_time_sec"] / result["logging_calls"] * 1000
        if result["logging_calls"] else 0.0
    )
    result["counter_avg_ms"] = (
        result["counter_time_sec"] / result["counter_calls"] * 1000
        if result["counter_calls"] else 0.0
    )

    return jsonify(result), 200


@app.route("/stats/reset", methods=["POST"])
def reset_stats():
    with stats_lock:
        stats["logging_calls"] = 0
        stats["logging_time_sec"] = 0.0
        stats["counter_calls"] = 0
        stats["counter_time_sec"] = 0.0

    return jsonify({"status": "reset"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)