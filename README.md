# Maksym Dzoban Software architecture lab 1

### **Task 1 - Базова архітектура мікросервисів**


**Архітектура** складається з трьох мікросервісів:
- facade-service - приймає POST/GET запити від клієнта
- logging-service - зберігає у пам’яті всі повідомлення які йому надходять, та може повертати їх
- messages-service - поки виступає у ролі заглушки, при звернені до нього повертає статичне повідомлення

**Клієнт взаємодіє з facade-service через HTTP POST та GET запити.**

Клієнт відправляє POST запит на facade-service, з певним текстовим повідомленням - msg. Отримавши повідомлення facade-service генерує для нього унікальний ідентифікатор UUID. Пара {UUID, msg} за допомогою програмного REST/HTTP-client у вигляді POST-повідомлення пересилається на logging-service. Logging-service отримавши повідомлення зберігає його та ідентифікатор у локальну хеш-таблицю (ідентифікатор - у якості ключа) та виводить у свою консоль отримане повідомлення.

**HTTP GET request flow:**

Клієнт відправляє GET запит на facade-service. Отримавши запит facade-service генерує GET-запити до logging-service та messages-service за допомогою програмного REST/HTTP-client. logging-service отримавши запит повертає всі повідомлення (без ключів) які зберігаються у хеш-таблиці у вигляді рядка messages-service отримавши запит повертає статичний текст, наприклад ‘not implemented yet’. facade-service отримавши відповіді від logging-service та messages-service конкатенує текст обох відповідей та повертає клієнту.

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



