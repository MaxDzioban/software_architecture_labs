# Lab 3 — Flask Microservices with Hazelcast

### Архітектура 

Система складається з:
- facade-service
- 3 instances of logging-service
- counter-service
- 3 Hazelcast nodes
- PostgreSQL

### Функціональність системи 
- facade-service приймає POST/GET запити
- logging-service зберігає транзакції в Hazelcast Distributed Map
- counter-service зберігає баланси і транзакції у PostgreSQL
- facade-service виконує load balancing та retry між logging-service instances


### Flow роботи системи

#### POST /transaction

1. Клієнт надсилає запит у facade-service
2. facade-service генерує transaction_id і timestamp
3. facade-service викликає counter-service:
   - оновлює баланс у PostgreSQL
4. facade-service викликає один із logging-service:
   - зберігає транзакцію в Hazelcast
5. facade-service повертає результат клієнту

---

#### GET /user/{user_id}

1. facade-service отримує баланс з counter-service
2. facade-service отримує транзакції з logging-service
3. повертає об’єднаний результат клієнту


## Запуск

```bash
docker compose up --build
```

Щоб зупинити сервіси (контейнери):

```bash
docker compose down
```

Зупинка одного Hazelcast node:

```bash
docker stop hazelcast-1
```

Результат - система продовжує працювати, дані не втрачаються.



---

## API

### POST транзакція

```bash
curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","amount":100}'
```

GET користувач `curl http://localhost:5000/user/u1`

GET всі акаунти ` curl http://localhost:5000/accounts`

Статистика ` curl http://localhost:5000/stats`


### Performance тест

```bash
python3 clients/load_test.py --scenario 1 --clients 5 --per-client 2000
python3 clients/load_test.py --scenario 2 --clients 5 --per-client 2000
```


## Результати 

Тестування продуктивності - сценарій 1

- 5 клієнтів × 2000 транзакцій (різні рахунки)

Total requests: 10000
Requests/sec: ~78
Всі результати коректні

--- 


Сценарій 2

- 5 клієнтів × 2000 транзакцій (один рахунок)

Total requests: 10000
Requests/sec: ~83
Баланс: 10000 (коректно)

Основна затримка — це counter-service (PostgreSQL). Hazelcast працює швидше (in-memory). retry дозволяє уникнути падіння системи. load balancing рівномірно розподіляє запити

