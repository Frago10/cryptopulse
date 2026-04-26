"""
Producer: Binance WebSocket  ->  Redpanda (topic `ticks`)

Se conecta al stream combinado de Binance y publica cada tick recibido
en Redpanda con la clave = símbolo (para que Redpanda lo particione
y mantenga orden por moneda).

Uso:
    python -m ingestion.streaming.binance_producer
    (Ctrl+C para detener limpiamente)

Endpoint de Binance usado:
    wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker/...

Payload ticker 24hr (selección de campos relevantes):
    s  = symbol      e.g. "BTCUSDT"
    E  = event time  ms since epoch
    c  = last price
    p  = price change (24h)
    P  = price change pct (24h)
    v  = base volume (24h)
    q  = quote volume (24h)
    n  = total trades (24h)
    b  = best bid
    a  = best ask

Aristas de producción implementadas:
  - Reconexión automática con backoff exponencial si se cae el WS.
  - Graceful shutdown con Ctrl+C (cierra flush del producer).
  - Métricas cada 10 s: mensajes recibidos / publicados / errores.
  - Acks completos (`acks=all`) para durabilidad.
"""
from __future__ import annotations

import asyncio
import json
import signal
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from confluent_kafka import Producer

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger

log = get_logger(__name__)


# -----------------------------------------------------------------
# Métricas en memoria (se resetean cada REPORT_SECONDS)
# -----------------------------------------------------------------
@dataclass
class Stats:
    received: int = 0
    published: int = 0
    errors: int = 0
    last_report: float = field(default_factory=time.time)

    def snapshot_and_reset(self) -> dict[str, Any]:
        now = time.time()
        dt = max(now - self.last_report, 1e-6)
        snap = {
            "received": self.received,
            "published": self.published,
            "errors": self.errors,
            "msgs_per_sec": round(self.received / dt, 1),
        }
        self.received = self.published = self.errors = 0
        self.last_report = now
        return snap


REPORT_SECONDS = 10


# -----------------------------------------------------------------
# Construcción del URL combinado
# -----------------------------------------------------------------
def build_stream_url() -> str:
    """
    Construye la URL del stream combinado de Binance con todos los símbolos
    del .env. Ejemplo resultado:
      wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker
    """
    # Binance espera minúsculas en la ruta
    streams = "/".join(f"{s.lower()}@ticker" for s in settings.symbols_list)
    base = settings.BINANCE_WS_URL.replace("/ws", "").rstrip("/")
    return f"{base}/stream?streams={streams}"


# -----------------------------------------------------------------
# Transformación del payload crudo -> dict normalizado
# -----------------------------------------------------------------
def normalize_ticker(raw: dict) -> dict:
    """Extrae los campos interesantes del ticker 24hr de Binance."""
    # El stream combinado envuelve el payload en {"stream": "...", "data": {...}}
    d = raw.get("data", raw)
    return {
        "symbol": d["s"],
        "event_time": int(d["E"]),           # ms since epoch
        "price": float(d["c"]),
        "price_change": float(d["p"]),
        "price_change_pct": float(d["P"]),
        "volume_base": float(d["v"]),
        "volume_quote": float(d["q"]),
        "trades_count": int(d["n"]),
        "bid": float(d["b"]),
        "ask": float(d["a"]),
        "open": float(d["o"]),
        "high": float(d["h"]),
        "low": float(d["l"]),
    }


# -----------------------------------------------------------------
# Delivery callback (confluent-kafka es async)
# -----------------------------------------------------------------
def make_delivery_callback(stats: Stats):
    def _cb(err, msg):
        if err is not None:
            stats.errors += 1
            log.error("kafka.delivery_failed", error=str(err))
        else:
            stats.published += 1
    return _cb


# -----------------------------------------------------------------
# Loop principal
# -----------------------------------------------------------------
async def consume_and_publish(producer: Producer, stats: Stats, stop_event: asyncio.Event) -> None:
    url = build_stream_url()
    backoff = 1.0
    delivery_cb = make_delivery_callback(stats)

    log.info("producer.connect", url=url, symbols=settings.symbols_list)

    while not stop_event.is_set():
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                log.info("producer.connected")
                backoff = 1.0
                async for raw_msg in ws:
                    if stop_event.is_set():
                        break
                    stats.received += 1
                    try:
                        payload = json.loads(raw_msg)
                        tick = normalize_ticker(payload)
                    except Exception as exc:
                        stats.errors += 1
                        log.error("producer.parse_failed", error=str(exc))
                        continue

                    producer.produce(
                        topic=settings.KAFKA_TOPIC_TICKS,
                        key=tick["symbol"],
                        value=json.dumps(tick).encode("utf-8"),
                        callback=delivery_cb,
                    )
                    # Procesar callbacks sin bloquear el loop
                    producer.poll(0)
        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning("producer.ws_disconnected", error=str(exc), retry_in=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # cap 30s
        except Exception as exc:
            log.error("producer.fatal", error=str(exc))
            stats.errors += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def report_loop(stats: Stats, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(REPORT_SECONDS)
        snap = stats.snapshot_and_reset()
        log.info("producer.stats", **snap)


async def main() -> None:
    configure_logging()
    stats = Stats()
    stop_event = asyncio.Event()

    # Registrar señales para shutdown limpio (en Windows solo funciona SIGINT)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # En Windows add_signal_handler no soporta SIGTERM; nos basta SIGINT
            pass

    producer = Producer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",
        "compression.type": "snappy",
        "linger.ms": 50,
        "batch.num.messages": 1000,
        "client.id": "cryptopulse-binance-producer",
    })

    try:
        await asyncio.gather(
            consume_and_publish(producer, stats, stop_event),
            report_loop(stats, stop_event),
        )
    finally:
        log.info("producer.shutdown.flushing")
        producer.flush(10)
        log.info("producer.shutdown.done")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
