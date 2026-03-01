import os
import time
import hazelcast

CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701,hz2:5701,hz3:5701").split(",")

MAP_NAME = "demo-map"
KEY = "key"
ITER = 10_000

def main():
    client = hazelcast.HazelcastClient(cluster_name=CLUSTER_NAME, cluster_members=MEMBERS)
    m = client.get_map(MAP_NAME).blocking()
    m.put_if_absent(KEY, 0)

    t0 = time.perf_counter()
    for _ in range(ITER):
        v = m.get(KEY)
        v += 1
        m.put(KEY, v)
    dt = time.perf_counter() - t0

    print(f"Client done: +{ITER} in {dt:.3f}s")
    client.shutdown()

if __name__ == "__main__":
    main()
