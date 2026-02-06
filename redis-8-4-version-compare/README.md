## Performance Improvements upon upgrading to Redis 8.4.x

Goal: to validate how much difference is there between the 2 versions.

Date: 06-02-2026

### Test setup

Kubmin Version: `v0.36.1`

Redis Versions: `8.2.1` and `8.4.0`

### How to run the tests

1. Deploy simple Deployment (`replicas=1`) with Redis 8.2.1
```shell
kubectl apply -f deployment-redis-before.yaml
```

2. Run the performance tests using `redis-benchmark`
```shell
kubectl apply -f benchmark-exec-workload.yaml
```


3. Deploy simple Deployment (`replicas=1`) with Redis 8.4.0
```shell
kubectl apply -f deployment-redis-after.yaml
```


Wait for the hourly data to populate in points 2 and 3, then compare the results.

