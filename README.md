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

## Запуск
```bash
docker compose up --build