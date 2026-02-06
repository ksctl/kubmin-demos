#!/usr/bin/env python3
"""
Continuous Redis Benchmark - Runs like a real workload
"""

import os
import sys
import json
import time
import redis
import random
import string
from datetime import datetime


def get_timestamp():
    """Get ISO timestamp with millisecond precision."""
    return datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'


def connect_redis(host, port):
    """Connect to Redis server."""
    try:
        client = redis.Redis(host=host, port=port, db=0, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        print(f"Failed to connect to Redis at {host}:{port}: {e}")
        sys.exit(1)


def throughput_benchmark(r, num_ops=1000000):
    """Run throughput benchmark: 90% GET, 10% SET."""
    print(f"\n=== Throughput Benchmark ({num_ops:,} ops) ===")

    # Populate initial keys
    print("Populating keys...")
    num_keys = 10000
    for i in range(num_keys):
        r.set(f"key:{i}", "value" * 100)

    # Run mixed workload
    print("Running workload (90% GET, 10% SET)...")
    start_time = time.time()
    start_ts = get_timestamp()

    for i in range(num_ops):
        key = f"key:{random.randint(0, num_keys-1)}"
        if random.random() < 0.9:
            r.get(key)
        else:
            r.set(key, "value" * 100)

    end_time = time.time()
    end_ts = get_timestamp()
    duration = end_time - start_time
    ops_per_sec = num_ops / duration

    # Get memory info
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)

    print(f"Duration: {duration:.2f}s")
    print(f"Ops/sec: {ops_per_sec:,.0f}")
    print(f"Memory: {memory_mb:.2f} MB")
    print(f"Timestamps: {start_ts} to {end_ts}")


def json_memory_benchmark(r):
    """Test JSON memory footprint."""
    print(f"\n=== JSON Memory Benchmark ===")

    # Test 1: Numeric arrays
    print("Testing numeric arrays...")
    num_keys = 100
    for i in range(num_keys):
        arr = [random.randint(0, 100) for _ in range(10000)]
        r.set(f"json:nums:{i}", json.dumps(arr))

    time.sleep(1)
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)
    print(f"Numeric arrays memory: {memory_mb:.2f} MB")

    # Test 2: String arrays (clear numeric first)
    print("Clearing numeric arrays...")
    r.flushdb()
    time.sleep(1)

    print("Testing string arrays...")
    for i in range(num_keys):
        arr = [''.join(random.choices(string.ascii_lowercase, k=5)) for _ in range(500)]
        r.set(f"json:strs:{i}", json.dumps(arr))

    time.sleep(1)
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)
    print(f"String arrays memory: {memory_mb:.2f} MB")


def run_benchmark_cycle(r, workload_size, iteration):
    """Run one complete benchmark cycle."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK ITERATION #{iteration}")
    print(f"{'='*60}")

    # Flush all data for clean start
    print("Flushing Redis for fresh cycle...")
    r.flushdb()

    # Throughput benchmark
    throughput_benchmark(r, workload_size)

    # JSON memory benchmark
    json_memory_benchmark(r)

    print(f"\n{'='*60}")
    print(f"ITERATION #{iteration} COMPLETE")
    print(f"{'='*60}")


def main():
    """Main entry point - runs continuously."""
    # Configuration from environment
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', '6379'))
    workload_size = int(os.getenv('WORKLOAD_SIZE', '1000000'))
    cycle_interval = int(os.getenv('CYCLE_INTERVAL_SECONDS', '300'))

    print("="*60)
    print("CONTINUOUS REDIS BENCHMARK")
    print("="*60)
    print(f"Redis: {redis_host}:{redis_port}")
    print(f"Workload: {workload_size:,} ops")
    print(f"Cycle interval: {cycle_interval}s")
    print(f"Mode: CONTINUOUS (runs forever)")
    print("="*60)

    # Connect to Redis
    r = connect_redis(redis_host, redis_port)
    info = r.info()
    redis_version = info.get('redis_version', 'unknown')
    print(f"Connected to Redis {redis_version}")
    print(f"\nStarting continuous benchmark loop...")

    # Run continuously
    iteration = 1
    while True:
        try:
            run_benchmark_cycle(r, workload_size, iteration)

            # Wait before next cycle
            print(f"\nWaiting {cycle_interval}s before next cycle...")
            time.sleep(cycle_interval)

            iteration += 1

        except KeyboardInterrupt:
            print("\n\nReceived interrupt signal. Shutting down gracefully...")
            break
        except Exception as e:
            print(f"\n\nError in benchmark cycle: {e}")
            print("Retrying in 30 seconds...")
            time.sleep(30)
            # Try to reconnect
            try:
                r = connect_redis(redis_host, redis_port)
            except:
                print("Reconnection failed. Exiting.")
                sys.exit(1)

    print("\nBenchmark stopped.")


if __name__ == '__main__':
    main()
