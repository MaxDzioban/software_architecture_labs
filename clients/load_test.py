import time
import json
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

FACADE_URL = os.getenv("FACADE_URL", "http://localhost:5000")

def do_posts(user_id: str, count: int, amount: int):
    session = requests.Session()
    ok = 0
    for _ in range(count):
        response = session.post(
            f"{FACADE_URL}/transaction",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "user_id": user_id,
                "amount": amount
            }),
            timeout=10
        )
        if response.status_code == 200:
            ok += 1
    return ok

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, choices=[1, 2], required=True)
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--per-client", type=int, default=10000)
    parser.add_argument("--amount", type=int, default=1)
    args = parser.parse_args()

    requests.post(f"{FACADE_URL}/stats/reset", timeout=5)
    requests.post("http://localhost:5002/reset", timeout=5)
    if args.scenario == 1:
        user_ids = [f"user_{i}" for i in range(args.clients)]
    else:
        user_ids = ["one_user"] * args.clients
    total_requests = args.clients * args.per_client
    start = time.perf_counter()
    ok_total = 0
    with ThreadPoolExecutor(max_workers=args.clients) as executor:
        futures = [
            executor.submit(do_posts, user_ids[i], args.per_client, args.amount)
            for i in range(args.clients)
        ]
        for future in as_completed(futures):
            ok_total += future.result()
    elapsed = time.perf_counter() - start
    rps = total_requests / elapsed if elapsed > 0 else 0.0
    stats = requests.get(f"{FACADE_URL}/stats", timeout=5).json()

    print("=== RESULT ===")
    print(f"Scenario: {args.scenario}")
    print(f"Clients: {args.clients}, per_client: {args.per_client}, total_requests: {total_requests}")
    print(f"OK responses: {ok_total}")
    print(f"Total time (sec): {elapsed:.4f}")
    print(f"Requests/sec: {rps:.2f}")

    print("\n=== FACADE REMOTE CALL CONTRIBUTION ===")
    print(
        f"logging calls: {stats['logging_calls']}, "
        f"total time sec: {stats['logging_time_sec']:.4f}, "
        f"avg ms: {stats['logging_avg_ms']:.3f}"
    )
    print(
        f"counter calls: {stats['counter_calls']}, "
        f"total time sec: {stats['counter_time_sec']:.4f}, "
        f"avg ms: {stats['counter_avg_ms']:.3f}"
    )

    if args.scenario == 1:
        expected = args.per_client * args.amount
        bad_accounts = 0
        for user_id in user_ids:
            balance = requests.get(f"{FACADE_URL}/user/{user_id}", timeout=5).json()["balance"]
            if balance != expected:
                bad_accounts += 1

        print("\nBalance check:")
        print(f"expected={expected}, bad_accounts={bad_accounts}/{args.clients}")

    else:
        expected = args.clients * args.per_client * args.amount
        balance = requests.get(f"{FACADE_URL}/user/one_user", timeout=5).json()["balance"]

        print("\nBalance check:")
        print(f"expected={expected}, actual={balance}")

if __name__ == "__main__":
    main()
