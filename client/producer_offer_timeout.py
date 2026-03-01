import os
import time
import hazelcast

CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701,hz2:5701,hz3:5701").split(",")

QNAME = "bounded-queue"

def main():
    client = hazelcast.HazelcastClient(cluster_name=CLUSTER_NAME, cluster_members=MEMBERS)
    q = client.get_queue(QNAME).blocking()

    for i in range(1, 101):
        ok = q.offer(i, timeout=1)
        print(f"OFFER {i}: ok={ok}, queue_size={q.size()}")
        if not ok:
            print("Queue is full and no consumers -> offer timed out.")
            break

    client.shutdown()

if __name__ == "__main__":
    main()
