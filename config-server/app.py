from flask import Flask, request, jsonify
from threading import Lock

app = Flask(__name__)

registry = {}
lock = Lock()


@app.route("/register", methods=["POST"])
def register_service():
    data = request.get_json(force=True, silent=False)

    service_name = data.get("service_name")
    address = data.get("address")

    if not service_name or not address:
        return jsonify({"error": "service_name and address are required"}), 400

    with lock:
        if service_name not in registry:
            registry[service_name] = []
        if address not in registry[service_name]:
            registry[service_name].append(address)

    return jsonify({
        "status": "registered",
        "service_name": service_name,
        "address": address,
        "instances": registry[service_name]
    }), 200


@app.route("/services/<service_name>", methods=["GET"])
def get_service_instances(service_name):
    with lock:
        instances = registry.get(service_name, [])

    return jsonify({
        "service_name": service_name,
        "instances": instances
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)