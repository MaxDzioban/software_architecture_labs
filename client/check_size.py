import os, hazelcast
client = hazelcast.HazelcastClient(
  cluster_name=os.getenv("HZ_CLUSTER_NAME","dev"),
  cluster_members=os.getenv("HZ_MEMBERS","hz1:5701,hz2:5701,hz3:5701").split(",")
)
m = client.get_map("demo-map").blocking()
print("demo-map size =", m.size())
client.shutdown()
