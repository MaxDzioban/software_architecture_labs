# Software Architecture Lab 2 

Maksym Dzoban

This lab demonstrates the usage of Hazelcast distributed in-memory data structures using a 3-node cluster and Python client.

Covered topics:
- Distributed Map
- Fault tolerance (node failures)
- Concurrent updates (no lock / pessimistic / optimistic)
- Bounded Distributed Queue

### Start cluster 

```bash
docker compose up -d --build
```

### Open Management Center

```bash
http://localhost:8080
```

# Part 1 — Distributed Map

Fill map with data:

```bash
docker compose exec py-client python 01_fill_map.py
```

Check size:

```bash
docker compose exec py-client python check_size.py
```

Result: demo-map size = 1001

**Data Distribution** -  In Management Center: data is distributed across 3 nodes = ~330 entries per node

**Fault Tolerance:** 

1 node down

```bash
docker stop hz2
```

2 nodes down (graceful):

```bash
docker stop hz2
docker stop hz3
```

**Data preserved (with backup-count=2)**

2 nodes crash : `docker kill -s KILL hz2 hz3`. Result - before fix of yaml file: demo-map size < 1001. 

After reconfiguration in `hazelcast.yaml` - `backup-count: 2`. Final result = `demo-map size = 1001`.


# Part 2 - Concurrent Updates

Without Locks: run 3 clients simultaneously:

Run 3 clients simultaneously:

```bash
docker compose exec py-client python reset_key.py
```

(3 terminals)

```bash
docker compose exec py-client python inc_no_lock.py
```

Then:

```bash
docker compose exec py-client python read_key.py
```

**Result:**

```bash
demo-map[key] < 30000
```

**Explanation = Lost updates due to race conditions (non-atomic read-modify-write)**


### Pessimistic Lock

Run this script:

```bash
docker compose exec py-client python reset_key.py
```


In 3 terminals:

```bash
/usr/bin/time -p docker compose exec py-client python inc_pessimistic_lock.py
```

**Result:** demo-map[key] = 30000

### Optimistic Lock (CAS)

Run this script:

```bash
docker compose exec py-client python reset_key.py
```

Run this in 3 different terminals:

```bash
/usr/bin/time -p docker compose exec py-client python inc_optimistic_cas.py
```

**Result:** demo-map[key] = 30000

| Method           | Result   | Speed  |
| ---------------- | -------- | ------ |
| No lock          |  <30000 | Fast   |
| Pessimistic lock |  30000  | Slower |
| Optimistic lock  |  30000  | Medium |

Details and logs are in explained in a report!


## Part 3 — Bounded Queue

Configuration:

```yaml
queue:
  bounded-queue:
    max-size: 10
```

Run consumers (2 terminals):

```bash
docker compose exec py-client python consumer_take.py
```


Run producer:

```bash
docker compose exec py-client python producer_put_with_stop.py
```


**Result:** each message is processed only once, messages distributed between consumers.

#### Behavior when queue is full

Run WITHOUT consumers: 

```bash
docker compose exec py-client python producer_put.py
```

**Result:** stops at element 10, blocks on 11th insert.

##### Alternative (timeout):

```bash
docker compose exec py-client python producer_offer_timeout.py
```

**Conclusions**
- Hazelcast distributes data across nodes automatically
- backup configuration ensures fault tolerance
- Without locking → data is inconsistent
- Pessimistic locking → safe but slower
- Optimistic locking → safe and more efficient
