"""
Consumer: Redpanda (topic `ticks`) -> Postgres (tabla `raw.ticks`)

Lee del topic `ticks` en consumer-group y hace batch inserts en Postgres.
Commita offsets solo después de una inserción exitosa (at-least-once
semantics — si algo falla, el mismo batch se reintenta al reiniciar).

Uso:
    python -m ingestion.streaming.redpanda_consumer
    (Ctrl+C para detener limpiamente)

Detalles de diseño:
  - Batch size dinámico: flush cuando se llenan BATCH_SIZE mensajes O
    pasan BATCH_TIMEOUT segundos (lo primero que ocurra).
  - psycopg2 `execute_values` con COPY-like throughput (hasta ~50k
    rows/s en hardware modesto).
  - Offsets commiteados DESPUÉS del insert -> no hay pérdida de datos
    si el consumer crashea.
  - Log de métricas cada 10s.
  - Dead-letter logging: mensajes mal formados se loggean pero no
    matan el proceso.
"""
from __future__ import annotations

import json
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import psycopg2
from confluent_kafka import Consumer, KafkaError, TopicPartition
from psycopg2.extras import execute_values

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger

log = get_logger(__name__)

# -----------------------------------------------------------------
# Parámetros del batching
# -----------------------------------------------------------------
BATCH_SIZE = 500
BATCH_TIMEOUT = 5.0       # segundos
POLL_TIMEOUT = 1.0        # segundos
REPORT_SECONDS = 10

INSERT_SQL = """
    INSERT INTO raw.ticks (
        symbol, event_time, price, price_change_pct,
        volume_base, volume_quote, trades_count, bid, ask, ingested_at
    ) VALUES %s
"""


@dataclass
class Stats:
    consumed: int = 0
    inserted: int = 0
    errors: int = 0
    dead_letters: int = 0
    last_report: float = field(default_factory=time.time)

    def snapshot_and_reset(self) -> dict[str, Any]:
        now = time.time()
        dt = max(now - self.last_report, 1e-6)
        snap = {
            "consumed": self.consumed,
            "inserted": self.inserted,
            "errors": self.errors,
            "dead_letters": self.dead_letters,
            "msgs_per_sec": round(self.inserted / dt, 1),
        }
        self.consumed = self.inserted = self.errors = self.dead_letters = 0
        self.last_report = now
        return snap


def msg_to_row(msg_value: bytes) -> tuple | None:
    """Convierte un mensaje JSON de Kafka en una tupla para INSERT."""
    try:
        t = json.loads(msg_value)
        return (
            t["symbol"],
            datetime.fromtimestamp(t["event_time"] / 1000, tz=timezone.utc),
            t["price"],
            t["price_change_pct"],
            t["volume_base"],
            t["volume_quote"],
            t["trades_count"],
            t["bid"],
            t["ask"],
            datetime.now(timezone.utc),
        )
    except Exception as exc:
        log.error("consumer.bad_message", error=str(exc))
        return None


def flush_batch(
    pg_conn,
    rows: list[tuple],
    offsets: list[TopicPartition],
    consumer: Consumer,
    stats: Stats,
) -> None:
    """Inserta `rows` en Postgres y commitea offsets si sale OK."""
    if not rows:
        return
    try:
        with pg_conn.cursor() as cur:
            execute_values(cur, INSERT_SQL, rows, page_size=500)
        pg_conn.commit()
        stats.inserted += len(rows)
        # Commitear offsets SOLO tras inserción exitosa (at-least-once)
        if offsets:
            consumer.commit(offsets=offsets, asynchronous=False)
    except Exception as exc:
        pg_conn.rollback()
        stats.errors += 1
        log.error("consumer.flush_failed", rows=len(rows), error=str(exc))


def report_if_due(stats: Stats) -> None:
    if time.time() - stats.last_report >= REPORT_SECONDS:
        snap = stats.snapshot_and_reset()
        log.info("consumer.stats", **snap)


# -----------------------------------------------------------------
# Loop principal
# -----------------------------------------------------------------
def run() -> None:
    configure_logging()

    # Shutdown flag mutable por signal handler
    shutdown = {"stop": False}

    def _on_signal(signum, _frame):
        log.info("consumer.signal_received", signal=signum)
        shutdown["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except AttributeError:
        pass  # Windows no siempre soporta SIGTERM

    # ---- Kafka Consumer ----
    consumer = Consumer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "cryptopulse-ticks-consumer",
        "enable.auto.commit": False,          # commit manual tras insert OK
        "auto.offset.reset": "earliest",
        "client.id": "cryptopulse-consumer-1",
        "session.timeout.ms": 30000,
    })
    consumer.subscribe([settings.KAFKA_TOPIC_TICKS])
    log.info("consumer.subscribed", topic=settings.KAFKA_TOPIC_TICKS)

    # ---- Postgres ----
    pg_conn = psycopg2.connect(settings.postgres_dsn)
    log.info("consumer.pg_connected", dsn_host=settings.POSTGRES_HOST)

    batch_rows: list[tuple] = []
    batch_offsets: dict[tuple[str, int], int] = {}  # (topic, partition) -> max offset + 1
    last_flush = time.time()
    stats = Stats()

    try:
        while not shutdown["stop"]:
            msg = consumer.poll(POLL_TIMEOUT)
            now = time.time()

            if msg is not None:
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    log.error("consumer.poll_error", error=str(msg.error()))
                    stats.errors += 1
                    continue

                stats.consumed += 1
                row = msg_to_row(msg.value())
                if row is None:
                    stats.dead_letters += 1
                else:
                    batch_rows.append(row)
                    # trackear el offset MÁS ALTO por partición
                    key = (msg.topic(), msg.partition())
                    batch_offsets[key] = max(batch_offsets.get(key, -1), msg.offset() + 1)

            # Flush si llenamos batch o pasó timeout
            should_flush = (
                len(batch_rows) >= BATCH_SIZE
                or (batch_rows and (now - last_flush) >= BATCH_TIMEOUT)
            )
            if should_flush:
                offsets_list = [
                    TopicPartition(t, p, off)
                    for (t, p), off in batch_offsets.items()
                ]
                flush_batch(pg_conn, batch_rows, offsets_list, consumer, stats)
                batch_rows.clear()
                batch_offsets.clear()
                last_flush = now

            report_if_due(stats)

    finally:
        log.info("consumer.shutdown.flushing_last")
        # Flush final de lo que quedó en memoria
        if batch_rows:
            offsets_list = [
                TopicPartition(t, p, off)
                for (t, p), off in batch_offsets.items()
            ]
            flush_batch(pg_conn, batch_rows, offsets_list, consumer, stats)
        consumer.close()
        pg_conn.close()
        log.info("consumer.shutdown.done")


if __name__ == "__main__":
    run()
