import json
import os
import time
import requests
import hazelcast

from flask import Flask, request, jsonify

app = Flask(__name__)

INSTANCE_NAME = os.getenv("INSTANCE_NAME", "logging-service")
HAZELCAST_SERVICE = os.getenv("HAZELCAST_SERVICE", "hazelcast")
HAZELCAST_PORT = int(os.getenv("HAZELCAST_PORT", "5701"))
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
                instances.append(f"{address['ip']}:{port['port']}")

    return instances


def get_hazelcast_members():
    members = get_kubernetes_endpoints(HAZELCAST_SERVICE)
    if members:
        return members
    return [f"{HAZELCAST_SERVICE}:{HAZELCAST_PORT}"]

hazelcast_client = hazelcast.HazelcastClient(
    cluster_members=get_hazelcast_members()
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

    print(f"[{INSTANCE_NAME}] Received POST: id={tx_id} user={data['user_id']} amount={data['amount']}")
    transactions_map.put(tx_id, value)
    print(f"[{INSTANCE_NAME}] Saved to Hazelcast")

    return jsonify({
        "status": "ok",
        "instance": INSTANCE_NAME
    }), 200


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