import os
import time
import hazelcast

CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701,hz2:5701,hz3:5701").split(",")

QNAME = "bounded-queue"

def main():
    client = hazelcast.HazelcastClient(cluster_name=CLUSTER_NAME, cluster_members=MEMBERS)
    q = client.get_queue(QNAME).blocking()

    print("start")
    while True:
        item = q.take()
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] GOT {item}, remaining size={q.size()}")
        if item == -1:
            print("Consumer received STOP signal.")
            break

    client.shutdown()

if __name__ == "__main__":
    main()
