"""
Crea los topics necesarios en Redpanda.

Se ejecuta UNA sola vez al arrancar el proyecto (o cada vez que agregamos
un topic). Es idempotente: si el topic ya existe, no falla.

Uso:
    python -m ingestion.streaming.create_topics

Topics creados:
    ticks           -> 6 particiones, replicación 1 (1 broker)
                       Datos crudos del WebSocket de Binance.
"""
from __future__ import annotations

from confluent_kafka.admin import AdminClient, NewTopic

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger

log = get_logger(__name__)

TOPICS = [
    NewTopic(settings.KAFKA_TOPIC_TICKS, num_partitions=6, replication_factor=1),
]


def main() -> None:
    configure_logging()
    admin = AdminClient({"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS})

    existing = set(admin.list_topics(timeout=10).topics.keys())
    log.info("topics.existing", topics=sorted(existing))

    to_create = [t for t in TOPICS if t.topic not in existing]
    if not to_create:
        log.info("topics.nothing_to_do")
        return

    futures = admin.create_topics(to_create)
    for topic, fut in futures.items():
        try:
            fut.result()
            log.info("topic.created", topic=topic)
        except Exception as exc:
            log.error("topic.create_failed", topic=topic, error=str(exc))


if __name__ == "__main__":
    main()
