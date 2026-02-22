import time
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

FACADE = "http://localhost:5000"

def do_posts(user_id: str, count: int, amount: int):
    s = requests.Session()
    ok = 0
    for _ in range(count):
        r = s.post(
            f"{FACADE}/transaction",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"user_id": user_id, "amount": amount}),
            timeout=10,)
        if r.status_code == 200:
            ok += 1
    return ok

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clients", type=int, default=10)
    p.add_argument("--per-client", type=int, default=10000)
    p.add_argument("--amount", type=int, default=1)
    p.add_argument("--scenario", type=int, choices=[1, 2], required=True)
    args = p.parse_args()

    requests.post(f"{FACADE}/stats/reset", timeout=5)
    requests.post("http://localhost:5002/reset", timeout=5)
    clients = args.clients
    per_client = args.per_client
    amount = args.amount

    if args.scenario == 1:
        user_ids = [f"user_{i}" for i in range(clients)]
    else:
        user_ids = ["one_user"] * clients

    total_requests = clients * per_client

    t0 = time.perf_counter()
    ok_total = 0
    with ThreadPoolExecutor(max_workers=clients) as ex:
        futures = [ex.submit(do_posts, user_ids[i], per_client, amount) for i in range(clients)]
        for f in as_completed(futures):
            ok_total += f.result()
    t1 = time.perf_counter()

    elapsed = t1 - t0
    rps = total_requests / elapsed if elapsed > 0 else 0.0

    stats = requests.get(f"{FACADE}/stats", timeout=5).json()

    print(f"Scenario: {args.scenario}")
    print(f"Clients: {clients}, per_client: {per_client}, total_requests: {total_requests}")
    print(f"OK responses: {ok_total}")
    print(f"Total time (sec): {elapsed:.4f}")
    print(f"Requests/sec: {rps:.2f}")
    print(f"logging calls: {stats['logging_calls']}, total time sec: {stats['logging_time_sec']:.4f}, avg ms: {stats['logging_avg_ms']:.3f}")
    print(f"counter  calls: {stats['counter_calls']}, total time sec: {stats['counter_time_sec']:.4f}, avg ms: {stats['counter_avg_ms']:.3f}")

    if args.scenario == 1:
        expected = per_client * amount
        bad = 0
        for uid in user_ids:
            bal = requests.get(f"{FACADE}/user/{uid}", timeout=5).json()["balance"]
            if bal != expected:
                bad += 1
        print()
        print(f"Balance check: expected={expected}, bad_accounts={bad}/{clients}")
    else:
        expected = (clients * per_client) * amount
        bal = requests.get(f"{FACADE}/user/one_user", timeout=5).json()["balance"]
        print()
        print(f"Balance check: expected={expected}, actual={bal}")

if __name__ == "__main__":
    main()
