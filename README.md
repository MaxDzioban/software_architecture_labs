# Maksym Dzoban Software architecture lab 1

### **Task 1 - Базова архітектура мікросервисів**

Система складається з трьох сервісів:
- facade-service — приймає запити від клієнта
- logging-service — зберігає всі транзакції
- counter-service — рахує баланс користувачів

Взаємодія між сервісами відбувається через HTTP (REST API).

### Запуск

В папці проекту
```{bash}
docker compose up --build
```


Перевірка роботи сервісів
```{bash}
http://localhost:5000/health
```
Очікуваний результат - {"status":"ok"}

Приклад транзакції:
```{bash}
curl -X POST http://localhost:5000/transaction -H "Content-Type: application/json" -d '{"user_id":"u1", "amount":-30}'
```

