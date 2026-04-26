"""
pages/01_Live_Tick_Tail.py
--------------------------
Tail en vivo de raw.ticks + semaforo de salud del streaming.

Auto-refresh: re-ejecuta el script cada `refresh_secs` para que las
queries (con TTL=10s/30s en lib/db.py) traigan datos frescos.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from dashboard.lib.db import fetch_recent_ticks, fetch_tick_summary


st.set_page_config(page_title="Live Tick Tail", page_icon="📡", layout="wide")
st.title("📡 Live Tick Tail")
st.caption("Auto-refresh cada N segundos. Vista cruda de `raw.ticks`.")

# ----- Controles -----
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    n_ticks = st.number_input("Ultimos N ticks", 10, 500, value=50, step=10)
with c2:
    refresh_secs = st.slider("Refresh (s)", 5, 60, value=10)
with c3:
    auto_refresh = st.toggle("Auto-refresh", value=True)

# ----- Resumen por simbolo (semaforo) -----
st.subheader("Salud por simbolo")
summary = fetch_tick_summary()

if summary.empty:
    st.warning("`raw.ticks` esta vacia. Arranca el producer: `make stream-producer`.")
else:
    # Semaforo: verde <5min, amarillo <15min, rojo >=15min
    def _color(mins: float) -> str:
        if pd.isna(mins):
            return "⚪"
        if mins < 5:
            return "🟢"
        if mins < 15:
            return "🟡"
        return "🔴"

    summary["status"] = summary["minutes_since_last"].apply(_color)
    summary["minutes_since_last"] = summary["minutes_since_last"].round(2)
    st.dataframe(
        summary[["status", "symbol", "ticks_total", "last_tick_at", "minutes_since_last"]],
        use_container_width=True,
        hide_index=True,
    )

# ----- Tail crudo -----
st.subheader("Tail")
ticks = fetch_recent_ticks(int(n_ticks))
if ticks.empty:
    st.info("Sin filas que mostrar.")
else:
    # Casteos para que numerico se muestre limpio
    ticks["price"] = ticks["price"].astype(float)
    ticks["volume_base"] = ticks["volume_base"].astype(float)
    if "spread" in ticks.columns:
        ticks["spread"] = ticks["spread"].astype(float)
    st.dataframe(ticks, use_container_width=True, hide_index=True)

# ----- Auto-refresh -----
# Truco simple: dormir N segundos y st.rerun(). En Streamlit moderno se podria
# usar st.experimental_fragment, pero esto funciona bien para 1 pagina chica.
if auto_refresh:
    placeholder = st.empty()
    placeholder.caption(f"Proximo refresh en {refresh_secs}s…")
    time.sleep(refresh_secs)
    st.rerun()
