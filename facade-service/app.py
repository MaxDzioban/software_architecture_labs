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

SERVICE_HOST = os.getenv("SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "5000"))
HAZELCAST_SERVICE = os.getenv("HAZELCAST_SERVICE", "hazelcast")
HAZELCAST_PORT = int(os.getenv("HAZELCAST_PORT", "5701"))
QUEUE_NAME = os.getenv("QUEUE_NAME", "counter-queue")
LOGGING_SERVICE_NAME = os.getenv("LOGGING_SERVICE_NAME", "logging-service")
LOGGING_SERVICE_PORT = int(os.getenv("LOGGING_SERVICE_PORT", "5001"))
COUNTER_SERVICE_NAME = os.getenv("COUNTER_SERVICE_NAME", "counter-service")
COUNTER_SERVICE_PORT = int(os.getenv("COUNTER_SERVICE_PORT", "5002"))

KUBE_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
KUBE_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
KUBE_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBE_SERVICE_HOST = os.getenv("KUBERNETES_SERVICE_HOST")
KUBE_SERVICE_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")


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

    instances = []
    for subset in data.get("subsets", []):
        ports = subset.get("ports", [])
        addresses = subset.get("addresses", [])
        for address in addresses:
            for port in ports:
                instances.append(f"http://{address['ip']}:{port['port']}")

    return instances


def get_service_instances(service_name: str, default_port: int):
    instances = get_kubernetes_endpoints(service_name)
    if instances:
        return instances
    return [f"http://{service_name}:{default_port}"]


def get_hazelcast_members():
    members = []
    if running_in_cluster():
        endpoints = get_kubernetes_endpoints(HAZELCAST_SERVICE)
        for endpoint in endpoints:
            members.append(endpoint.replace("http://", ""))
    if not members:
        members.append(f"{HAZELCAST_SERVICE}:{HAZELCAST_PORT}")
    return members

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=get_hazelcast_members()
)
counter_queue = hazelcast_client.get_queue(QUEUE_NAME).blocking()

stats_lock = Lock()
stats = {
    "logging_calls": 0,
    "logging_time_sec": 0.0,
    "counter_calls": 0,
    "counter_time_sec": 0.0,
    "counter_queue_puts": 0,
    "counter_queue_time_sec": 0.0,
    "config_calls": 0,
    "config_time_sec": 0.0,
}


def add_stat(service_name: str, elapsed: float):
    with stats_lock:
        if service_name == "logging":
            stats["logging_calls"] += 1
            stats["logging_time_sec"] += elapsed
        elif service_name == "counter_queue":
            stats["counter_queue_puts"] += 1
            stats["counter_queue_time_sec"] += elapsed
            stats["counter_calls"] += 1
            stats["counter_time_sec"] += elapsed
        elif service_name == "config":
            stats["config_calls"] += 1
            stats["config_time_sec"] += elapsed


def timed_request(method: str, url: str, **kwargs):
    start = time.perf_counter()
    response = requests.request(method, url, timeout=5, **kwargs)
    elapsed = time.perf_counter() - start
    return response, elapsed


def call_logging_with_retry(method: str, path: str, **kwargs):
    endpoints = get_service_instances(LOGGING_SERVICE_NAME, LOGGING_SERVICE_PORT)
    random.shuffle(endpoints)

    last_error = None
    for base_url in endpoints:
        try:
            url = f"{base_url}{path}"
            response, elapsed = timed_request(method, url, **kwargs)
            add_stat("logging", elapsed)
            if response.status_code < 500:
                return response
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise RuntimeError("All logging-service instances failed")


def call_counter_get(path: str):
    endpoints = get_service_instances(COUNTER_SERVICE_NAME, COUNTER_SERVICE_PORT)
    base_url = random.choice(endpoints)

    response, _ = timed_request("GET", f"{base_url}{path}")
    return response


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
    result["counter_avg_ms"] = (
        result["counter_time_sec"] / result["counter_calls"] * 1000
        if result["counter_calls"] else 0.0
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
        stats["counter_calls"] = 0
        stats["counter_time_sec"] = 0.0
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