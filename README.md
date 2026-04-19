# Lab 4 — Flask Microservices with Messaging Queue

## Опис
У цьому проєкті реалізована мікросервісна система на Flask з:
- config-server
- facade-service
- 3 instances of logging-service
- counter-service
- Hazelcast cluster
- PostgreSQL

## Основна ідея
POST запити до counter-service виконуються асинхронно через Hazelcast Queue.

- facade-service = producer
- counter-service = consumer

## Архітектура
- facade-service приймає POST/GET запити
- logging-service зберігає транзакції в Hazelcast Map
- counter-service зчитує транзакції з Hazelcast Queue і оновлює PostgreSQL
- config-server зберігає адреси мікросервісів

## Запуск і приклад використання:
```bash
docker compose up --build
```

```bash
curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","amount":100}'

curl http://localhost:5000/user/u1

curl http://localhost:5000/accounts
```

```bash
curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","amount":50}'

curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u2","amount":30}'

curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","amount":-20}'
```

```bash
for i in {1..10}; do
  curl -X POST http://localhost:5000/transaction \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"u3\",\"amount\":1}"
done
```

Перевірка логів

```bash
docker logs logging-service-1
docker logs logging-service-2
docker logs logging-service-3
```


```bash
curl http://localhost:5005/services/facade-service
curl http://localhost:5005/services/logging-service
curl http://localhost:5005/services/counter-service
```

Зупинка сервісу

```bash
docker pause counter-service
```


Перевірка транзакцій поки виключений

```bash
curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u4","amount":10}'

curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u4","amount":20}'

curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u4","amount":30}'
```

GET during failure

```bash
curl http://localhost:5000/user/u4
curl http://localhost:5000/accounts
```

Resume service

```bash
docker unpause counter-service
```

