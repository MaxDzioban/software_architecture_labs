import os
import hazelcast

CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MEMBERS = os.getenv("HZ_MEMBERS", "hz1:5701").split(",")

def main():
    client = hazelcast.HazelcastClient(
        cluster_name=CLUSTER_NAME,
        cluster_members=MEMBERS,
    )

    m = client.get_map("demo-map").blocking()

    # 0..1000 включно => 1001 значення
    for k in range(0, 1001):
        m.put(str(k), f"value-{k}")

    print("Inserted:", m.size(), "entries into demo-map")

    client.shutdown()

if __name__ == "__main__":
    main()
