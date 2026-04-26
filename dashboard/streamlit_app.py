"""
streamlit_app.py
----------------
Entry point de la app Streamlit (CryptoPulse Lab).

Por que existe esta app si ya hay un Power BI:
  Power BI brilla en lectura ejecutiva. Streamlit brilla en interactividad
  python-nativa: tail en vivo de raw.ticks y un agente LLM que explica
  alertas. Las dos herramientas son complementarias, no redundantes.

Estructura (Streamlit multipage):
  dashboard/
    streamlit_app.py             <- Home (este archivo)
    pages/
      01_Live_Tick_Tail.py       <- streaming health + tail de ticks
      02_Alert_Explainer.py      <- selecciona alerta -> Claude la explica
    lib/
      db.py                      <- helpers de Postgres con cache
      llm.py                     <- cliente Anthropic + prompt builder

Uso:
    streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit no incluye la raiz del repo en sys.path; lo agregamos aqui
# para que `from ingestion.utils...` y `from dashboard.lib...` resuelvan.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from ingestion.utils.config import settings


st.set_page_config(
    page_title="CryptoPulse Lab",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("CryptoPulse Lab")
st.caption(
    "App complementaria al dashboard de Power BI. "
    "Pensada para inspeccion en vivo y exploracion con LLM."
)

# ----- Banderas de estado en sidebar -----
with st.sidebar:
    st.subheader("Estado del entorno")

    # Postgres: ping rapido (via fetch_df para que respete commit/rollback)
    try:
        from dashboard.lib.db import fetch_df
        fetch_df("SELECT 1 AS ok")
        st.success("Postgres conectado")
    except Exception as e:
        st.error(f"Postgres: {type(e).__name__}")
        st.caption(str(e))

    # Anthropic: solo verifica que la key este seteada
    if settings.ANTHROPIC_API_KEY:
        st.success(f"LLM listo - {settings.ANTHROPIC_MODEL}")
    else:
        st.warning("ANTHROPIC_API_KEY no seteada - el Alert Explainer no funcionara")

    st.divider()
    st.caption("Navega usando las paginas de arriba")

# ----- Body: explicacion + atajos -----
col1, col2 = st.columns(2, gap="large")

with col1:
    st.subheader("Live Tick Tail")
    st.write(
        "Tail en vivo (auto-refresh cada 10s) de `raw.ticks`, con resumen "
        "por simbolo y semaforo de salud del streaming. Util para verificar "
        "que el producer Binance -> Redpanda -> Postgres esta latiendo."
    )
    st.page_link("pages/01_Live_Tick_Tail.py", label="Abrir Live Tick Tail")

with col2:
    st.subheader("Alert Explainer (LLM)")
    st.write(
        "Selecciona una alerta de `bi.v_anomaly_alerts` y un modelo Claude "
        "te devuelve una explicacion estructurada: senales tecnicas, "
        "contexto de mercado, hipotesis. Pensado para acelerar el triage "
        "de outliers."
    )
    st.page_link("pages/02_Alert_Explainer.py", label="Abrir Alert Explainer")

st.divider()
with st.expander("Arquitectura"):
    st.markdown(
        """
        ```
        Streamlit (esta app)
              |  psycopg2 (via dashboard.lib.db)
              v
          Postgres (schema bi.* y raw.*)
              ^
              |  pipeline horario (Airflow)
              |
        Binance WS  +  CoinGecko REST  +  Reddit  +  F&G
        ```

        - **DB shared**: la app NO duplica logica - consume las mismas
          vistas `bi.*` que Power BI.
        - **LLM**: solo se invoca on-demand desde el Alert Explainer.
          No se mandan ticks ni datos en bulk al modelo.
        """
    )
