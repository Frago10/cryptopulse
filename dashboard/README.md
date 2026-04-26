# Dashboard — CryptoPulse

Dos vistas complementarias sobre la capa `bi.*` de Postgres.

| App | Para que | Como se levanta |
|---|---|---|
| **Power BI** (`powerbi/`) | Reporting ejecutivo, KPIs, drill-down visual. | Power BI Desktop + `cryptopulse.pbix` |
| **Streamlit** (`streamlit_app.py`) | Inspeccion en vivo (tail de ticks) + Alert Explainer con LLM (Claude). | `make streamlit` |

## Streamlit — quick start

1. Asegurate de tener el stack arriba (`make up`) y al menos una corrida del pipeline (`make silver-e2e`).
2. Setea `ANTHROPIC_API_KEY` en `.env` (consigue una en https://console.anthropic.com/settings/keys).
3. Instala la dep nueva:

   ```powershell
   pip install anthropic==0.40.0
   ```

4. Corre:

   ```powershell
   make streamlit
   # o: streamlit run dashboard/streamlit_app.py
   ```

5. Abre http://localhost:8501.

## Estructura

```
dashboard/
├── powerbi/                  # Fase 8
│   ├── queries.m
│   ├── measures.dax
│   ├── layout_spec.md
│   └── README.md
├── streamlit_app.py          # Home
├── pages/
│   ├── 01_Live_Tick_Tail.py
│   └── 02_Alert_Explainer.py
└── lib/
    ├── db.py                 # PgClient cache + queries
    └── llm.py                # Anthropic + prompt builder
```

## Detalles tecnicos

- Las queries SQL viven solo en `dashboard/lib/db.py`. Si una vista nueva entra a `bi.*`, agrega el fetch aqui.
- El cliente Anthropic se cachea con `st.cache_resource` (singleton por proceso).
- Los DataFrames se cachean con `st.cache_data(ttl=...)` para no martillar Postgres.
- Modelo por defecto: `claude-haiku-4-5-20251001`. Cambia `ANTHROPIC_MODEL` en `.env` si quieres otro (ej. `claude-sonnet-4-6` para mayor calidad a mayor costo).

## Troubleshooting

**`ModuleNotFoundError: dashboard`** — corres `streamlit run` desde otra ruta. Hazlo siempre desde la raiz del repo.

**`The connection is dropped` cuando recargas en vivo** — Postgres tumbo la sesion vieja. Refresca el navegador, el `PgClient` se reconecta solo.

**Pagina Alert Explainer dice "no hay alertas"** — corre primero `make ml-anomalies && make dbt-run` para poblar `bi.v_anomaly_alerts`.
