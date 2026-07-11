import os
import sys
import json
import time
import logging
import redis
import random
import string
from datetime import datetime
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger(__name__)


def configure_telemetry():
    """Configure OTLP/gRPC telemetry from standard OTEL_* environment variables."""
    resource = Resource.create({
        "service.name": os.environ["OTEL_SERVICE_NAME"],
        "service.namespace": os.environ["POD_NAMESPACE"],
        "service.version": os.environ["OTEL_SERVICE_VERSION"],
        "deployment.environment.name": os.environ["DEPLOYMENT_ENVIRONMENT_NAME"],
    })

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(logger_provider)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

    meter = metrics.get_meter("redis-benchmark")
    return (
        trace.get_tracer("redis-benchmark"),
        meter.create_counter(
            "redis_benchmark_operations_total",
            unit="{redis-operation}",
            description="Successful GET and SET commands in the benchmark workload.",
        ),
    )


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
        logger.error("Failed to connect to Redis at %s:%s: %s", host, port, e)
        sys.exit(1)


def throughput_benchmark(r, redis_operations, metric_attributes, num_ops=1000000):
    """Run throughput benchmark: 90% GET, 10% SET."""
    logger.info("=== Throughput Benchmark (%s ops) ===", f"{num_ops:,}")

    # Populate initial keys
    logger.info("Populating keys...")
    num_keys = 10000
    for i in range(num_keys):
        r.set(f"key:{i}", "value" * 100)

    # Run mixed workload
    logger.info("Running workload (90%% GET, 10%% SET)...")
    start_time = time.time()
    start_ts = get_timestamp()

    for i in range(num_ops):
        key = f"key:{random.randint(0, num_keys-1)}"
        if random.random() < 0.9:
            r.get(key)
        else:
            r.set(key, "value" * 100)
        redis_operations.add(1, metric_attributes)

    end_time = time.time()
    end_ts = get_timestamp()
    duration = end_time - start_time
    ops_per_sec = num_ops / duration

    # Get memory info
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)

    logger.info("Duration: %.2fs", duration)
    logger.info("Ops/sec: %s", f"{ops_per_sec:,.0f}")
    logger.info("Memory: %.2f MB", memory_mb)
    logger.info("Timestamps: %s to %s", start_ts, end_ts)


def json_memory_benchmark(r):
    """Test JSON memory footprint."""
    logger.info("=== JSON Memory Benchmark ===")

    # Test 1: Numeric arrays
    logger.info("Testing numeric arrays...")
    num_keys = 100
    for i in range(num_keys):
        arr = [random.randint(0, 100) for _ in range(10000)]
        r.set(f"json:nums:{i}", json.dumps(arr))

    time.sleep(1)
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)
    logger.info("Numeric arrays memory: %.2f MB", memory_mb)

    # Test 2: String arrays (clear numeric first)
    logger.info("Clearing numeric arrays...")
    r.flushdb()
    time.sleep(1)

    logger.info("Testing string arrays...")
    for i in range(num_keys):
        arr = [''.join(random.choices(string.ascii_lowercase, k=5)) for _ in range(500)]
        r.set(f"json:strs:{i}", json.dumps(arr))

    time.sleep(1)
    info = r.info('memory')
    memory_mb = info.get('used_memory_rss', 0) / (1024 * 1024)
    logger.info("String arrays memory: %.2f MB", memory_mb)


def run_benchmark_cycle(r, redis_operations, metric_attributes, workload_size, iteration):
    """Run one complete benchmark cycle."""
    logger.info("%s", "=" * 60)
    logger.info("BENCHMARK ITERATION #%s", iteration)
    logger.info("%s", "=" * 60)

    # Flush all data for clean start
    logger.info("Flushing Redis for fresh cycle...")
    r.flushdb()

    # Throughput benchmark
    throughput_benchmark(r, redis_operations, metric_attributes, workload_size)

    # JSON memory benchmark
    json_memory_benchmark(r)

    logger.info("%s", "=" * 60)
    logger.info("ITERATION #%s COMPLETE", iteration)
    logger.info("%s", "=" * 60)


def main():
    """Main entry point - runs continuously."""
    tracer, redis_operations = configure_telemetry()
    metric_attributes = {"pod": os.environ["POD_NAME"]}

    # Configuration from environment
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', '6379'))
    workload_size = int(os.getenv('WORKLOAD_SIZE', '1000000'))
    cycle_interval = int(os.getenv('CYCLE_INTERVAL_SECONDS', '300'))

    logger.info("%s", "=" * 60)
    logger.info("CONTINUOUS REDIS BENCHMARK")
    logger.info("%s", "=" * 60)
    logger.info("Redis: %s:%s", redis_host, redis_port)
    logger.info("Workload: %s ops", f"{workload_size:,}")
    logger.info("Cycle interval: %ss", cycle_interval)
    logger.info("Mode: CONTINUOUS (runs forever)")
    logger.info("%s", "=" * 60)

    # Connect to Redis
    r = connect_redis(redis_host, redis_port)
    info = r.info()
    redis_version = info.get('redis_version', 'unknown')
    logger.info("Connected to Redis %s", redis_version)
    logger.info("Starting continuous benchmark loop...")

    # Run continuously
    iteration = 1
    while True:
        try:
            with tracer.start_as_current_span("redis.benchmark.iteration") as span:
                span.set_attribute("benchmark.iteration", iteration)
                run_benchmark_cycle(
                    r,
                    redis_operations,
                    metric_attributes,
                    workload_size,
                    iteration,
                )

            # Wait before next cycle
            logger.info("Waiting %ss before next cycle...", cycle_interval)
            time.sleep(cycle_interval)

            iteration += 1

        except KeyboardInterrupt:
            logger.info("Received interrupt signal. Shutting down gracefully...")
            break
        except Exception as e:
            logger.exception("Error in benchmark cycle: %s", e)
            logger.info("Retrying in 30 seconds...")
            time.sleep(30)
            # Try to reconnect
            try:
                r = connect_redis(redis_host, redis_port)
            except:
                logger.error("Reconnection failed. Exiting.")
                sys.exit(1)

    logger.info("Benchmark stopped.")


if __name__ == '__main__':
    main()
