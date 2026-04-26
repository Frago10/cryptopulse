"""
alerts/telegram_notifier.py
---------------------------
Notificador de alertas a Telegram.

Flujo:
  1. SELECT de alertas elegibles desde bi.v_anomaly_alerts:
       - is_anomaly_consensus = TRUE
       - severity >= MIN_SEVERITY (parametro)
       - event_hour >= NOW() - LOOKBACK_HOURS
       - NOT EXISTS en alerts.telegram_sent (dedup idempotente)
  2. Para cada alerta nueva:
       - construir mensaje (resumen + opcional LLM explanation)
       - POST a Telegram Bot API
       - registrar en alerts.telegram_sent

Uso:
  python -m alerts.telegram_notifier
  python -m alerts.telegram_notifier --min-severity 3 --lookback-hours 6 --no-llm
  python -m alerts.telegram_notifier --dry-run    # no manda nada, solo log

Requisitos en .env:
  TELEGRAM_BOT_TOKEN  - obtenido de @BotFather
  TELEGRAM_CHAT_ID    - chat (privado o grupo) destino
  ANTHROPIC_API_KEY   - opcional, para incluir explicacion del LLM
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Optional

import requests

from ingestion.utils.config import settings
from ingestion.utils.logging_config import configure_logging, get_logger
from ingestion.utils.pg_client import get_pg

log = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ----------------------------------------------------------------------------
# Modelo
# ----------------------------------------------------------------------------
@dataclass
class Alert:
    """Subconjunto de columnas de bi.v_anomaly_alerts que necesitamos."""
    alert_key: str
    symbol: str
    coin_name: Optional[str]
    event_hour: object  # datetime
    price_close: Optional[float]
    hour_return_pct: Optional[float]
    return_zscore: Optional[float]
    severity: Optional[float]
    severity_bucket: Optional[str]
    detector_label: Optional[str]
    fng_value: Optional[int]
    fng_bucket: Optional[str]
    reddit_mentions_day: Optional[int]
    vader_compound_avg: Optional[float]


# ----------------------------------------------------------------------------
# Lectura de alertas
# ----------------------------------------------------------------------------
SELECT_NEW_ALERTS = """
    SELECT
        a.symbol || '|' || to_char(a.ts_hour AT TIME ZONE 'UTC', 'YYYYMMDDHH24MI')
                                                         AS alert_key,
        a.symbol,
        a.coin_name,
        a.ts_hour                                        AS event_hour,
        a.price_close,
        a.hour_return_pct,
        a.return_zscore,
        a.severity,
        a.severity_bucket,
        a.detector_label,
        a.fng_value,
        a.fng_bucket,
        a.reddit_mentions_day,
        a.vader_compound_avg
    FROM bi.v_anomaly_alerts a
    LEFT JOIN alerts.telegram_sent s ON s.alert_key =
        a.symbol || '|' || to_char(a.ts_hour AT TIME ZONE 'UTC', 'YYYYMMDDHH24MI')
    WHERE a.is_anomaly_consensus = TRUE
      AND COALESCE(a.severity, 0) >= %s
      AND a.ts_hour >= NOW() - %s::interval
      AND s.alert_key IS NULL
    ORDER BY a.ts_hour DESC, a.severity DESC NULLS LAST
"""


def fetch_pending_alerts(min_severity: float, lookback_hours: int) -> List[Alert]:
    pg = get_pg()
    with pg.transaction() as c, c.cursor() as cur:
        cur.execute(SELECT_NEW_ALERTS, (min_severity, f"{lookback_hours} hours"))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return [Alert(**dict(zip(cols, r))) for r in rows]


# ----------------------------------------------------------------------------
# Construccion del mensaje
# ----------------------------------------------------------------------------
def _fmt(value, suffix: str = "", nd: Optional[int] = None) -> str:
    if value is None:
        return "n/a"
    if nd is not None and isinstance(value, (int, float)):
        return f"{value:.{nd}f}{suffix}"
    return f"{value}{suffix}"


def build_basic_message(a: Alert) -> str:
    """Mensaje resumido (HTML parse mode)."""
    arrow = "📉" if (a.hour_return_pct or 0) < 0 else "📈"
    sev = _fmt(a.severity, nd=2)
    bucket = a.severity_bucket or "?"

    return (
        f"<b>{arrow} Anomaly · {a.symbol}</b>\n"
        f"<i>{a.coin_name or a.symbol}</i> · <b>{bucket}</b> (sev {sev})\n"
        f"\n"
        f"• Hora: <code>{a.event_hour}</code>\n"
        f"• Precio close: <code>{_fmt(a.price_close, nd=4)}</code>\n"
        f"• Retorno hora: <code>{_fmt(a.hour_return_pct, suffix=' %', nd=3)}</code>\n"
        f"• Z-score: <code>{_fmt(a.return_zscore, nd=2)}</code>\n"
        f"• Detector: <code>{_fmt(a.detector_label)}</code>\n"
        f"• Fear &amp; Greed: <code>{_fmt(a.fng_value)} ({_fmt(a.fng_bucket)})</code>\n"
        f"• Reddit mentions: <code>{_fmt(a.reddit_mentions_day)}</code>\n"
        f"• VADER avg: <code>{_fmt(a.vader_compound_avg, nd=3)}</code>\n"
    )


def maybe_add_llm_summary(message: str, a: Alert) -> str:
    """Si hay ANTHROPIC_API_KEY, agrega un parrafo con la explicacion del modelo."""
    if not settings.ANTHROPIC_API_KEY:
        return message
    try:
        from anthropic import Anthropic
    except ImportError:
        log.warning("telegram.llm.skip", reason="anthropic package not installed")
        return message

    prompt = (
        "Eres analista cripto. En 2-3 frases, en espanol, resume por que "
        "esta hora podria ser anomala. No des consejos de inversion. "
        "Datos:\n"
        f"- Simbolo: {a.symbol}\n"
        f"- Retorno hora: {a.hour_return_pct} %\n"
        f"- Z-score: {a.return_zscore}\n"
        f"- Severidad: {a.severity} ({a.severity_bucket})\n"
        f"- Detector: {a.detector_label}\n"
        f"- Fear & Greed: {a.fng_value} ({a.fng_bucket})\n"
        f"- VADER avg: {a.vader_compound_avg}\n"
    )
    try:
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Telegram HTML parse mode rechaza algunos chars; escapamos los basicos
        text = text.replace("<", "&lt;").replace(">", "&gt;")
        return f"{message}\n<b>🤖 Analisis</b>\n<i>{text}</i>"
    except Exception as e:  # noqa: BLE001
        log.warning("telegram.llm.error", err=str(e))
        return message


# ----------------------------------------------------------------------------
# Envio + dedup
# ----------------------------------------------------------------------------
def send_to_telegram(text: str, *, dry_run: bool) -> bool:
    if dry_run:
        log.info("telegram.dryrun", chars=len(text))
        return True
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        log.error("telegram.config.missing")
        return False
    url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=20)
    ok = r.ok and r.json().get("ok", False)
    if not ok:
        log.error("telegram.send.fail", status=r.status_code, body=r.text[:300])
    return ok


def mark_sent(alert: Alert, ok: bool) -> None:
    pg = get_pg()
    sql = """
        INSERT INTO alerts.telegram_sent
            (alert_key, symbol, event_hour, severity, response_ok)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (alert_key) DO NOTHING
    """
    with pg.transaction() as c, c.cursor() as cur:
        cur.execute(sql, (alert.alert_key, alert.symbol, alert.event_hour, alert.severity, ok))


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
def run(min_severity: float, lookback_hours: int, use_llm: bool, dry_run: bool) -> int:
    configure_logging()
    log.info(
        "telegram.start",
        min_severity=min_severity,
        lookback_hours=lookback_hours,
        use_llm=use_llm,
        dry_run=dry_run,
    )
    alerts = fetch_pending_alerts(min_severity, lookback_hours)
    log.info("telegram.candidates", count=len(alerts))

    sent = 0
    for a in alerts:
        msg = build_basic_message(a)
        if use_llm:
            msg = maybe_add_llm_summary(msg, a)
        ok = send_to_telegram(msg, dry_run=dry_run)
        if not dry_run:
            mark_sent(a, ok)
        if ok:
            sent += 1
        log.info("telegram.sent", alert_key=a.alert_key, ok=ok)
    log.info("telegram.done", sent=sent, candidates=len(alerts))
    return sent


def main() -> None:
    p = argparse.ArgumentParser(description="Manda alertas de anomalias a Telegram.")
    p.add_argument("--min-severity", type=float, default=3.0,
                   help="Severidad minima (default 3.0 = high).")
    p.add_argument("--lookback-hours", type=int, default=6,
                   help="Cuantas horas hacia atras revisar (default 6).")
    p.add_argument("--no-llm", action="store_true",
                   help="Omite la explicacion del LLM aunque haya API key.")
    p.add_argument("--dry-run", action="store_true",
                   help="No manda nada, solo loguea.")
    args = p.parse_args()
    run(
        min_severity=args.min_severity,
        lookback_hours=args.lookback_hours,
        use_llm=not args.no_llm,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
