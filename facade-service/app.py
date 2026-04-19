import json
import os
import time
import uuid
import random
import requests
import hazelcast

from threading import Lock
from flask import Flask, request, jsonify

app = Flask(__name__)

SERVICE_NAME = "facade-service"
SERVICE_HOST = os.getenv("SERVICE_HOST", "facade-service")
SERVICE_PORT = os.getenv("SERVICE_PORT", "5000")
CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://config-server:5005")

HAZELCAST_MEMBERS = os.getenv(
    "HAZELCAST_MEMBERS",
    "hazelcast-1:5701,hazelcast-2:5701,hazelcast-3:5701"
).split(",")

QUEUE_NAME = os.getenv("QUEUE_NAME", "counter-queue")

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=HAZELCAST_MEMBERS
)
counter_queue = hazelcast_client.get_queue(QUEUE_NAME).blocking()

stats_lock = Lock()
stats = {
    "logging_calls": 0,
    "logging_time_sec": 0.0,
    "counter_queue_puts": 0,
    "counter_queue_time_sec": 0.0,
    "config_calls": 0,
    "config_time_sec": 0.0
}


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
                print(f"[facade-service] Registered in config-server: {address}")
                return
        except Exception as e:
            print(f"[facade-service] Registration failed, retrying... {e}")
            time.sleep(2)

    raise RuntimeError("[facade-service] Could not register in config-server")


def add_stat(service_name: str, elapsed: float):
    with stats_lock:
        if service_name == "logging":
            stats["logging_calls"] += 1
            stats["logging_time_sec"] += elapsed
        elif service_name == "counter_queue":
            stats["counter_queue_puts"] += 1
            stats["counter_queue_time_sec"] += elapsed
        elif service_name == "config":
            stats["config_calls"] += 1
            stats["config_time_sec"] += elapsed


def timed_request(method: str, url: str, **kwargs):
    start = time.perf_counter()
    response = requests.request(method, url, timeout=5, **kwargs)
    elapsed = time.perf_counter() - start
    return response, elapsed


def get_service_instances(service_name: str):
    response, elapsed = timed_request("GET", f"{CONFIG_SERVER_URL}/services/{service_name}")
    add_stat("config", elapsed)

    if response.status_code != 200:
        raise RuntimeError(f"config-server failed for {service_name}")

    instances = response.json().get("instances", [])
    if not instances:
        raise RuntimeError(f"No instances found for service {service_name}")

    return instances


def call_logging_with_retry(method: str, path: str, **kwargs):
    endpoints = get_service_instances("logging-service")
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


def call_counter_get(path: str):
    instances = get_service_instances("counter-service")
    base_url = random.choice(instances)

    response, _ = timed_request("GET", f"{base_url}{path}")
    return response


register_in_config_server()


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
        logging_resp = call_logging_with_retry("POST", "/log", json=transaction)
    except Exception as e:
        return jsonify({"error": "all logging-service instances unavailable", "details": str(e)}), 502

    if logging_resp.status_code != 200:
        return jsonify({
            "error": "logging-service failed",
            "details": logging_resp.text
        }), 502

    try:
        start = time.perf_counter()
        counter_queue.put(json.dumps(transaction))
        elapsed = time.perf_counter() - start
        add_stat("counter_queue", elapsed)
    except Exception as e:
        return jsonify({"error": "failed to enqueue transaction", "details": str(e)}), 502

    return jsonify({
        "transaction_id": transaction["transaction_id"],
        "status": "queued"
    }), 200


@app.route("/user/<user_id>", methods=["GET"])
def get_user_info(user_id):
    try:
        counter_resp = call_counter_get(f"/balance/{user_id}")
    except Exception as e:
        balance = None
        counter_error = str(e)
    else:
        if counter_resp.status_code == 200:
            balance = counter_resp.json().get("balance", 0)
            counter_error = None
        else:
            balance = None
            counter_error = counter_resp.text

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
        "balance": balance,
        "transactions": logging_resp.json().get("transactions", []),
        "counter_error": counter_error
    }), 200


@app.route("/accounts", methods=["GET"])
def get_accounts():
    try:
        response = call_counter_get("/accounts")
    except Exception as e:
        return jsonify({"balances": None, "counter_error": str(e)}), 200

    if response.status_code != 200:
        return jsonify({"balances": None, "counter_error": response.text}), 200

    return jsonify(response.json()), 200


@app.route("/stats", methods=["GET"])
def get_stats():
    with stats_lock:
        result = dict(stats)

    result["logging_avg_ms"] = (
        result["logging_time_sec"] / result["logging_calls"] * 1000
        if result["logging_calls"] else 0.0
    )
    result["counter_queue_avg_ms"] = (
        result["counter_queue_time_sec"] / result["counter_queue_puts"] * 1000
        if result["counter_queue_puts"] else 0.0
    )
    result["config_avg_ms"] = (
        result["config_time_sec"] / result["config_calls"] * 1000
        if result["config_calls"] else 0.0
    )

    return jsonify(result), 200


@app.route("/stats/reset", methods=["POST"])
def reset_stats():
    with stats_lock:
        stats["logging_calls"] = 0
        stats["logging_time_sec"] = 0.0
        stats["counter_queue_puts"] = 0
        stats["counter_queue_time_sec"] = 0.0
        stats["config_calls"] = 0
        stats["config_time_sec"] = 0.0

    return jsonify({"status": "reset"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)