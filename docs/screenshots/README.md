# Screenshots — CryptoPulse

Captura tú las imágenes en tu Windows (yo no tengo acceso a tu pantalla). Sigue la guía de abajo: para cada slot hay (a) qué tiene que mostrar la imagen, (b) cómo llegar a esa pantalla, (c) cómo capturarla.

Cuando tengas las imágenes, déjalas en este folder con el nombre **exacto** que indica la columna **Filename** — el `README.md` raíz y la `GUIA_COMPLETA.md` ya las referencian con esos nombres.

## Cómo capturar en Windows

Tres opciones, de mejor a más rápida:

1. **`Win + Shift + S`** → Snipping Tool (Snip&Sketch). Selecciona área. Pega en Paint, guarda como PNG en este folder.
2. **`Win + PrtSc`** → screenshot de pantalla completa, va a `Pictures/Screenshots/`. Cópialo y renómbralo aquí.
3. **`Alt + PrtSc`** → screenshot de la ventana activa.

Recomendación: usar `Win + Shift + S`, recortar lo justo, guardar PNG.

---

## Slots

| # | Filename                          | Qué tiene que mostrar | Cómo llegar |
|---|-----------------------------------|------------------------|-------------|
| 1 | `01_docker_ps.png`                | `docker compose ps` con todos los servicios (postgres, minio, redpanda, airflow) en estado healthy. | PowerShell → `docker compose ps` → captura la ventana entera. |
| 2 | `02_minio_console.png`            | MinIO Console mostrando los buckets `bronze`, `silver`, `gold` con archivos `.parquet` adentro. | Navegador → http://localhost:9001 → login `minio` / `minio12345` → click en bucket `bronze`. |
| 3 | `03_redpanda_topic.png`           | Redpanda UI con el topic `ticks` y el throughput de mensajes recientes. | Navegador → http://localhost:8080 → click en `ticks`. |
| 4 | `04_airflow_dag_hourly.png`       | Vista grid (treeview) del DAG `cryptopulse_hourly` con todos los TaskGroups en verde. | Navegador → http://localhost:8081 → click en `cryptopulse_hourly` → tab Grid. |
| 5 | `05_airflow_dag_graph.png`        | Vista graph del mismo DAG (TaskGroups encadenados: ingest → transform → ml → validate → data_quality → notify). | Igual que (4) pero tab Graph. |
| 6 | `06_psql_bi_views.png`            | Salida de `\dv bi.*` mostrando las 5 vistas: v_kpi_latest, v_price_hourly, v_anomaly_alerts, v_sentiment_daily, v_market_snapshot_latest. | `docker compose exec postgres psql -U cryptopulse -d cryptopulse` → `\dv bi.*` |
| 7 | `07_powerbi_executive.png`        | Página 1 del Power BI (Executive Summary) con las 5 KPI cards renderizadas y el line chart de precios. | Power BI Desktop → tu .pbix → tab Executive Summary. |
| 8 | `08_powerbi_anomalies.png`        | Página 2 (Price Anomalies) con la tabla de log y el donut por detector. | Mismo .pbix, tab Price Anomalies. |
| 9 | `09_powerbi_sentiment.png`        | Página 3 (Sentiment Tracker) con las líneas F&G y VADER. | Mismo .pbix, tab Sentiment Tracker. |
| 10 | `10_powerbi_market.png`          | Página 4 (Market Overview) con la tabla tipo CoinGecko. | Mismo .pbix, tab Market Overview. |
| 11 | `11_streamlit_home.png`          | Streamlit Lab home con sidebar verde "Postgres conectado" y "LLM listo". | `streamlit run dashboard/streamlit_app.py` → http://localhost:8501 |
| 12 | `12_streamlit_live_tail.png`     | Página Live Tick Tail con tabla de salud por símbolo (semáforos) y tail crudo. | Página 1 en la sidebar de Streamlit. |
| 13 | `13_streamlit_alert_explainer.png`| Página Alert Explainer con un alert seleccionada, el mini-gráfico de precio, y la respuesta de Claude renderizada. | Página 2 en la sidebar de Streamlit + click "Explicar esta alerta". |
| 14 | `14_telegram_test.png`           | Chat de Telegram con el mensaje de smoke test ("Test · CryptoPulse pipeline alerts wired up") visible. | Telegram (mobile o desktop) → conversación con tu bot. |
| 15 | `15_telegram_alert.png`          | Chat de Telegram con un mensaje real de alerta (con la sección 🤖 Análisis del LLM si tienes ANTHROPIC_API_KEY). | Igual que (14), después de que un DAG haya disparado una alerta real, o forzando con `--min-severity 0`. |
| 16 | `16_github_actions.png`          | Workflow `CI` corriendo verde en GitHub Actions tab. | Tab Actions del repo en GitHub → último run del workflow CI. |

## Tips para que se vean profesionales

- **Resolución**: mínimo 1280×800. Más alto es mejor.
- **Modo claro u oscuro**: consistente entre todas. Power BI elige el que se vea mejor con tus colores.
- **Sin información personal**: si tu chat_id o el nombre real del bot es sensible, blur con cualquier editor (Paint 3D, Photoshop, Figma).
- **Compresión**: PNG sin compresión agresiva. Tiny PNG si pesan mucho (>1MB). El repo soporta PNGs grandes pero idealmente < 500KB cada uno.
- **Crop limpio**: incluye lo justo. Una buena screenshot del Power BI no necesita mostrar la barra de tareas de Windows.

## Vista previa esperada en el README

Una vez completes el folder, podemos sumar una sección al `README.md` raíz con:

```markdown
## Demos

| Power BI Executive | Streamlit Lab | Telegram Alert |
|---|---|---|
| ![](docs/screenshots/07_powerbi_executive.png) | ![](docs/screenshots/11_streamlit_home.png) | ![](docs/screenshots/15_telegram_alert.png) |
```

Cuando tengas las screenshots, avísame y yo monto esa sección en el README.
