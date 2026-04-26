"""
pages/02_Alert_Explainer.py
---------------------------
Selecciona una alerta de bi.v_anomaly_alerts -> Claude la explica.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from dashboard.lib.db import fetch_anomaly_alerts, fetch_price_window
from dashboard.lib.llm import AlertContext, explain_alert
from ingestion.utils.config import settings


st.set_page_config(page_title="Alert Explainer", page_icon="🤖", layout="wide")
st.title("🤖 Alert Explainer")
st.caption(
    "Cada alerta horaria de `bi.v_anomaly_alerts` puede mandarse al modelo "
    "Claude para una explicacion en lenguaje natural."
)

if not settings.ANTHROPIC_API_KEY:
    st.error(
        "Falta `ANTHROPIC_API_KEY` en `.env`. Crea una en "
        "https://console.anthropic.com/settings/keys y reinicia la app."
    )
    st.stop()

# ----- Selector de alertas -----
alerts = fetch_anomaly_alerts(limit=200)

if alerts.empty:
    st.info(
        "Aun no hay alertas registradas. Corre el pipeline ML primero:\n\n"
        "`make ml-anomalies && make dbt-run`"
    )
    st.stop()

c1, c2 = st.columns([1, 1])
with c1:
    only_consensus = st.toggle(
        "Solo consensus (mayor precision)", value=True,
        help="Filtra alertas marcadas por z-score AND IsolationForest.",
    )
with c2:
    severity_min = st.slider(
        "Severidad minima", 0.0, 10.0, value=0.0, step=0.5,
    )

filtered = alerts.copy()
if only_consensus:
    filtered = filtered[filtered["is_anomaly_consensus"] == True]  # noqa: E712
filtered = filtered[filtered["severity"].fillna(0) >= severity_min]

if filtered.empty:
    st.warning("Ninguna alerta cumple los filtros. Reduce severidad o desactiva consensus.")
    st.stop()

st.subheader(f"Alertas disponibles ({len(filtered)})")
filtered_display = filtered.copy()
filtered_display["price_close"] = filtered_display["price_close"].astype(float).round(4)
filtered_display["hour_return_pct"] = filtered_display["hour_return_pct"].astype(float).round(3)
filtered_display["return_zscore"] = filtered_display["return_zscore"].astype(float).round(3)
filtered_display["severity"] = filtered_display["severity"].astype(float).round(2)

st.dataframe(
    filtered_display[
        [
            "ts_hour", "symbol", "coin_name",
            "price_close", "hour_return_pct", "return_zscore",
            "severity", "severity_bucket", "detector_label",
            "fng_bucket",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

# Indice como label legible: "BTC · 2026-04-25 13:00 · z=4.21"
def _label(row: pd.Series) -> str:
    return (
        f"{row['symbol']} · {pd.to_datetime(row['ts_hour']).strftime('%Y-%m-%d %H:%M')} "
        f"· z={float(row['return_zscore']):.2f} · sev={float(row['severity']):.2f}"
    )

filtered = filtered.reset_index(drop=True)
labels = filtered.apply(_label, axis=1)
choice = st.selectbox("Elige una alerta para explicar", options=labels.index, format_func=lambda i: labels.iloc[i])

selected = filtered.loc[choice]

# ----- Mini grafico de contexto -----
st.subheader("Contexto de precio (48h alrededor del evento)")
window = fetch_price_window(symbol=selected["symbol"], hours_back=48)
if not window.empty:
    chart_df = window[["ts_hour", "price_close"]].copy()
    chart_df["price_close"] = chart_df["price_close"].astype(float)
    chart_df = chart_df.set_index("ts_hour")
    st.line_chart(chart_df, height=240)
else:
    st.info("Sin ventana de precio para este simbolo (puede que la vista bi.v_price_hourly aun no tenga 48h).")

# ----- Explicacion -----
st.subheader("Explicacion del modelo")
if st.button("Explicar esta alerta", type="primary"):
    with st.spinner(f"Llamando a {settings.ANTHROPIC_MODEL}…"):
        ctx = AlertContext(alert_row=selected, price_window=window)
        text = explain_alert(ctx)
    st.markdown(text)
    with st.expander("Datos enviados al modelo"):
        st.json(
            {k: (str(v) if pd.notna(v) else None) for k, v in selected.to_dict().items()}
        )
else:
    st.caption("Click en el boton para invocar al LLM. Costo aproximado: < $0.01 por alerta.")
