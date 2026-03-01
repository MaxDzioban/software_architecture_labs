import os
import hazelcast

CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701,hz2:5701,hz3:5701").split(",")

MAP_NAME = "demo-map"
KEY = "key"

def main():
    client = hazelcast.HazelcastClient(cluster_name=CLUSTER_NAME, cluster_members=MEMBERS)
    m = client.get_map(MAP_NAME).blocking()

    val = m.get(KEY)
    print(f"{MAP_NAME}[{KEY}] =", val)

    client.shutdown()

if __name__ == "__main__":
    main()
