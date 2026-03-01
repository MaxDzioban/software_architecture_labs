import os
import hazelcast
CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701,hz2:5701,hz3:5701").split(",")

QNAME = "bounded-queue"

def main():
    client = hazelcast.HazelcastClient(cluster_name=CLUSTER_NAME, cluster_members=MEMBERS)
    q = client.get_queue(QNAME).blocking()

    q.clear()
    print(f"Cleared queue: {QNAME}, size={q.size()}")

    client.shutdown()

if __name__ == "__main__":
    main()
