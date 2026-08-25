# Redis 8.2.1, 8.4.0, and 8.6.1 comparison

This demo runs one continuous benchmark against a single Redis Deployment. The Redis manifests have the same workload identity, Service, labels, resources, and Kubmin `container-hour` measure; only the Redis image tag changes. Run the versions sequentially so that their observation windows do not overlap.

No measured results are stored in this repository. Use the blank templates below to record a reproduction; do not treat a presentation screenshot as raw benchmark output.

## Prerequisites

- A Kubernetes cluster accessible with `kubectl`, with permission to create Deployments and a Service in the chosen namespace.
- A Kubmin version that supports workload measure annotations and finalized image-version history, producing finalized data for annotated workloads. Record the exact version used.
- The OpenTelemetry collector endpoint expected by `benchmark-exec-workload.yaml` available at `opentelemetry-collector.kubmin.svc.cluster.local:4317`.
- Cluster egress or a registry mirror that can pull the Redis and benchmark images.
- A Linux AMD64 node for the benchmark image. The pinned benchmark image currently publishes only an AMD64 runtime manifest.
- A stable, preferably homogeneous node pool and enough uninterrupted time to collect the same number of complete Kubmin aggregation intervals for every version.

Run all commands from this directory and use one namespace throughout:

```shell
cd redis-8-4-version-compare
export NAMESPACE="<benchmark-namespace>"
```

Confirm the context and namespace before applying anything. Do not move a run between clusters, regions, namespaces, or node pools.

## Fixed inputs

The checked-in inputs are:

| Input | Fixed value |
| --- | --- |
| Redis Deployment | `redis-benchmark`, one replica, container `cache` |
| Redis Service | `redis-service:6379` |
| Redis labels | `app: redis-benchmark` and `kubmin.ksctl.com/workload: "true"` |
| Redis resources | request and limit: `250m` CPU and `250Mi` memory |
| Redis Kubmin measure | `container-hour` |
| Benchmark Deployment | `benchmark-app`, one replica |
| Benchmark image | `ghcr.io/dipankardas011/redis-8-4-0-vs-8-2-1:v12.0.1@sha256:cfb7ffe12c36101aa94bd784aeeb32b02a7398be31ef5efd45048cd8f88b852e` |
| Benchmark Kubmin measure | `redis-operation`, emitted by the benchmark container only |
| Benchmark workload | `1,000,000` measured GET/SET operations per cycle; `300` seconds between cycles |
| Redis 8.2.1 manifest | `deployment-redis-before.yaml`, pinned to `sha256:5fa2edb1e408fa8235e6db8fab01d1afaaae96c9403ba67b70feceb8661e8621` |
| Redis 8.4.0 manifest | `deployment-redis-after.yaml`, pinned to `sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78` |
| Redis 8.6.1 manifest | `deployment-redis-8-6-1.yaml`, pinned to `sha256:315270d166080f537bbdf1b489b603aaaa213cb55a544acfa51feb7481abb1c0` |

Before starting, choose one observation-window duration and one number of finalized aggregation intervals to use for all three versions. Keep the benchmark manifest and image, Redis configuration and resources, Kubmin version and allocation settings, energy/carbon data source, cluster region, and node type constant. The scheduler can still choose a different node, so record the actual node for every window.

## Procedure

### 1. Start Redis 8.2.1

```shell
kubectl --namespace "$NAMESPACE" apply -f deployment-redis-before.yaml
kubectl --namespace "$NAMESPACE" rollout status deployment/redis-benchmark
```

### 2. Deploy the benchmark once

```shell
kubectl --namespace "$NAMESPACE" apply -f benchmark-exec-workload.yaml
kubectl --namespace "$NAMESPACE" rollout status deployment/benchmark-app
```

Leave this Deployment in place for all three Redis runs. Do not rebuild, reapply, or change its image or configuration between versions. Kubernetes may restart its Pod during a Redis transition; if that happens, record the restart and exclude the affected interval.

Use the benchmark logs to confirm the steady-state gate referenced below. A timestamped `ITERATION #... COMPLETE` emitted after the Redis rollout is the completion marker.

```shell
kubectl --namespace "$NAMESPACE" logs deployment/benchmark-app --tail=200
```

### 3. Collect the Redis 8.2.1 window

Wait until the Redis rollout is complete and the benchmark has completed a post-rollout cycle successfully. Then follow the data-finalization and recording steps below. Do not deploy Redis 8.4.0 until the selected 8.2.1 window is finalized.

### 4. Replace Redis with 8.4.0 and collect its window

```shell
kubectl --namespace "$NAMESPACE" apply -f deployment-redis-after.yaml
kubectl --namespace "$NAMESPACE" rollout status deployment/redis-benchmark
```

Wait for a successful post-rollout benchmark cycle, then collect and record the same number of complete, finalized intervals used for 8.2.1. Exclude the rollout and reconnect period.

### 5. Replace Redis with 8.6.1 and collect its window

```shell
kubectl --namespace "$NAMESPACE" apply -f deployment-redis-8-6-1.yaml
kubectl --namespace "$NAMESPACE" rollout status deployment/redis-benchmark
```

Again, wait for a successful post-rollout benchmark cycle and collect the same number of complete, finalized intervals. Exclude the rollout and reconnect period.

## Finalization and run metadata

For each version:

1. Treat the rollout, image pull, Redis startup, benchmark reconnect, and first incomplete Kubmin bucket as transition data.
2. Start the comparison window at a Kubmin aggregation boundary that occurs after Redis is ready and the benchmark has completed a cycle successfully.
3. Wait until every bucket in the chosen window is final according to Kubmin's configured aggregation and ingestion delay. Never compare a current or partial bucket with a finalized bucket.
4. Record the exact UTC window start and end. Use equal-duration windows with the same aggregation granularity and number of buckets.
5. Record the resolved image digest and node, not only the image tag. After each rollout, this command prints those fields for the Redis Pod:

   ```shell
   kubectl --namespace "$NAMESPACE" get pods -l app=redis-benchmark \
     -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="cache")].image}{"\t"}{.status.containerStatuses[?(@.name=="cache")].imageID}{"\t"}{.spec.nodeName}{"\t"}{.status.containerStatuses[?(@.name=="cache")].state.running.startedAt}{"\n"}{end}'
   ```

6. Record the benchmark Pod's image digest and node as an additional check that the workload stayed fixed:

   ```shell
   kubectl --namespace "$NAMESPACE" get pods -l app=benchmark-app \
     -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[?(@.name=="benchmark")].imageID}{"\t"}{.spec.nodeName}{"\t"}{.status.containerStatuses[?(@.name=="benchmark")].state.running.startedAt}{"\n"}{end}'
   ```

If a Pod, resolved image digest, node type, Kubmin configuration, or telemetry source changes inside a window, discard or split that window rather than combining unlike conditions.

## Measurement boundary

The Redis `cache` container is configured with the `container-hour` measure. Its SCI and SEI values are therefore per container-hour, not per Redis operation. The `redis-operation` counter belongs to the separate `benchmark-app` workload and is useful for checking that each window received comparable load; Kubmin does not automatically transfer that denominator to the Redis workload.

Do not report Redis energy, SCI, or SEI per operation from this setup. That requires an explicitly validated Redis-side custom measure and is outside this demo.

## Compare like for like

Compare only windows with the same duration, finalized-bucket count, benchmark configuration, functional unit, Redis resources and replica count, cluster location, node class, and Kubmin allocation/energy/carbon configuration. Check that the benchmark operation telemetry is complete for each window. If node hardware, contention, workload completion, telemetry coverage, or carbon/energy inputs differ, report the difference and do not attribute the result solely to the Redis version.

Kubmin cost is an allocation estimate based on configured pricing and allocation rules; it is not a cloud-provider invoice or direct measurement of marginal spend. Cloud energy data may be modeled rather than measured at the workload. SCI and SEI are meaningful comparisons only when their system boundary, functional unit, workload, time-window treatment, infrastructure conditions, and energy/carbon methodology are comparable.

## Results-recording template

Record provenance before copying values from Kubmin:

| Redis version | Resolved Redis image digest | Redis node / node type | Benchmark image digest | Benchmark node / node type | Window start (UTC) | Window end (UTC) | Aggregation intervals and finalization check/time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8.2.1 |  |  |  |  |  |  |  |
| 8.4.0 |  |  |  |  |  |  |  |
| 8.6.1 |  |  |  |  |  |  |  |

Record values together with the units and methodology shown by Kubmin:

| Redis version | Benchmark operations during window | Estimated Redis cost (value and currency) | Redis energy (value, unit, measured or modeled) | Redis SCI (per container-hour) | Redis SEI (per container-hour) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 8.2.1 |  |  |  |  |  |  |
| 8.4.0 |  |  |  |  |  |  |
| 8.6.1 |  |  |  |  |  |  |
