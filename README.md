# Lab 5 - Мікросервіси з використанням Service Discovery та Config Server на базі на базі Kubernetes (15 балів)


## Опис мікросервісів і компонентів системи
- facade-service
- logging-service (3 replicas)
- counter-service
- Hazelcast cluster
- PostgreSQL


- Kubernetes ConfigMap-based configuration
- Kubernetes service discovery via Endpoints


## Архітектура
- `facade-service` приймає POST/GET запити
- `logging-service` зберігає транзакції в Hazelcast Map
- `counter-service` читає транзакції з Hazelcast Queue і оновлює PostgreSQL
- `facade-service` динамічно знаходить `logging-service` і `counter-service` через Kubernetes Endpoints
- `logging-service` та `counter-service` динамічно знаходять Hazelcast через Kubernetes Endpoints
- Усі налаштування для сервісів зберігаються у `k8s/configmap.yaml`

## Запуск системи

1. Minikube:
   ```bash
   minikube start
   ```

2. Docker для використання Minikube як локального daemon:
   ```bash
   eval $(minikube docker-env)
   ```

3. Створити образи сервісів:
   ```bash
   docker build -t facade-service:latest ./facade-service
   docker build -t logging-service:latest ./logging-service
   docker build -t counter-service:latest ./counter-service
   ```

4. Розгорніть усі об'єкти Kubernetes із  `k8s`:
   ```bash
   kubectl apply -f k8s/
   ```

5. Стан розгортання:
   ```bash
   kubectl get pods -o wide
   kubectl get services
   ```

## Перевірка роботи

### Перевірка служб і endpoint'ів

```bash
kubectl get pods -l app=facade-service
kubectl get pods -l app=logging-service
kubectl get pods -l app=counter-service
kubectl get pods -l app=hazelcast

kubectl get endpoints logging-service
kubectl get endpoints counter-service
kubectl get endpoints hazelcast

kubectl get configmap app-config -o yaml
```

### Перевірка логів

```bash
kubectl logs deployment/facade-service
kubectl logs deployment/logging-service
kubectl logs deployment/counter-service
```

### Доступ до `facade-service`

- Через NodePort:
  ```bash
  minikube service facade-service --url
  ```
- Або через порт-форвардинг:
  ```bash
  kubectl port-forward service/facade-service 5000:5000
  ```

Після цього можна виконати запити:

```bash
curl -X POST http://localhost:5000/transaction \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","amount":100}'

curl http://localhost:5000/user/u1
curl http://localhost:5000/accounts
```

## Приклад роботи після перезапуску або вимкнення інстансу

1. Зменшення кількості реплік `logging-service`:
   ```bash
   kubectl scale deployment/logging-service --replicas=2
   ```

2. Перевірка endpoint'ів:
   ```bash
   kubectl get endpoints logging-service
   ```

3. Повторний запит через `facade-service` повинен успішно обробитися іншими інстанціями.

## Зупинка системи

```bash
kubectl delete -f k8s/
```


## Результати тестування продуктивності

Я провів фінальні тести продуктивності системи на Minikube, використовуючи `load_test.py` з параметрами:

- `--clients 10`
- `--per-client 100`
- `--amount 1`

- **Сценарій 1** = 10 акаунтів  
- **Сценарій 2** = 1 акаунт  

---

# Виміряні результати (final-task)

### Сценарій: 10 акаунтів

| Метрика                         | Task 1 (in-mem) | Task 3 (DB) | Task 5 (final) |
|--------------------------------|----------------|------------|----------------|
| Загальний час                  | 619.99 s       | ~128.2 s*  | 7.6042 s       |

**Внесок сервісів:**

- `logging-service`:  
  - Task 1: 1944.48 s (avg ~19.45 ms)  
  - Task 3: не проводились заміри 
  - Task 5: 14.0046 s (avg 14.005 ms)  

- `counter-service`:  
  - Task 1: 1918.68 s (avg ~19.19 ms)  
  - Task 3: не проводились заміри
  - Task 5: 6.0979 s (avg 6.098 ms)  

---

### Сценарій: 1 акаунт

| Метрика                         | Task 1 (in-mem) | Task 3 (DB) | Task 5 (final) |
|--------------------------------|----------------|------------|----------------|
| Загальний час                  | 620.28 s       | ~120.5 s*  | 7.8307 s       |

**Внесок сервісів:**

- `logging-service`:  
  - Task 1: 1948.84 s (avg ~19.49 ms)  
  - Task 3: не проводились заміри
  - Task 5: 12.6393 s (avg 12.639 ms)  

- `counter-service`:  
  - Task 1: 1923.75 s (avg ~19.24 ms)  
  - Task 3: не проводились заміри
  - Task 5: 7.8792 s (avg 7.879 ms)  

---

\* Для Task 3 загальний час на основі throughput (~78–83 req/sec для 10 000 запитів).

**Внесок сервісів:**

- `logging-service`:  
  - загалом: 12.6393 s  
  - середнє: 12.639 ms  

- `counter-service`:  
  - загалом: 7.8792 s  
  - середнє: 7.879 ms  

