# Power BI Dashboard — CryptoPulse

Dashboard ejecutivo sobre la capa `bi.*` de Postgres. Cuatro páginas: Executive Summary, Price Anomalies, Sentiment Tracker, Market Overview.

## Pre-requisitos

- **Power BI Desktop** (gratis en Windows, Microsoft Store)
- Stack CryptoPulse corriendo (`make up`) con al menos una corrida completa del pipeline (`make silver-e2e` + `make gold-ml-e2e`)
- Schema `bi` aplicado: `make bi-views`

## Arquitectura de datos

```
Power BI Desktop
      │  PostgreSQL.Database("localhost", "cryptopulse")
      ▼
  schema bi.*  ← vistas estables (este proyecto)
      │
      ▼
  schema analytics_marts.*  ← dbt models (cambiables)
      │
      ▼
  schema raw.* + ml.*  ← ingestion + VADER
```

**Por qué la capa `bi.*`**: si dbt renombra un mart o una columna, sólo actualizamos la vista en `04_bi_views.sql`. El `.pbix` del analista no se rompe. Es la lección del "decoupling de presentación" aplicada a BI.

## Setup paso a paso

### 1. Aplicar las vistas

```powershell
make bi-views
# o equivalente:
python -m ingestion.utils.pg_bootstrap --only 04_bi_views.sql
```

Verifica en psql:
```sql
\dv bi.*
-- debe mostrar: v_kpi_latest, v_price_hourly, v_anomaly_alerts,
--              v_sentiment_daily, v_market_snapshot_latest
```

### 2. Crear el `.pbix`

1. Abrir Power BI Desktop
2. **Get Data → PostgreSQL database**
   - Server: `localhost:5432`
   - Database: `cryptopulse`
   - Data Connectivity mode: **Import** (no DirectQuery)
3. Authentication: **Database**
   - User: `cryptopulse`
   - Password: ver `.env` (variable `POSTGRES_PASSWORD`)
   - Encryption: **disabled** (conexión local — en prod usar SSH tunnel)
4. En el navigator se listan los schemas. **NO** selecciones tablas aquí — cancela. Vamos a pegar las queries manualmente.
5. **Home → Transform data → Advanced Editor**. Para cada bloque de `queries.m`:
   - `Home → New Source → Blank Query`
   - `Advanced Editor` → pegar el snippet (solo el `let ... in ...`, sin el comentario del nombre)
   - Renombrar la query en el panel izquierdo con el nombre indicado (`KPI_Latest`, `PriceHourly`, etc.)
6. `Close & Apply`.

### 3. Modelo y relaciones

Ver [layout_spec.md](layout_spec.md) sección "Modelo de datos".

- Marcar `DateDim` como date table.
- Crear relaciones `DateDim[date]` → facts. Si hay mismatch de tipo (`datetimezone` vs `date`), agregar columna calculada `date` en cada fact.

### 4. Medidas DAX

Abrir [measures.dax](measures.dax) y copiar cada medida a la tabla que indica el comentario (`TABLA: X` arriba del bloque).

Mejor práctica: crear una tabla vacía llamada `_Measures` (`New table → _Measures = {BLANK()}`) y mover todas las medidas ahí para tenerlas agrupadas.

### 5. Páginas visuales

Seguir [layout_spec.md](layout_spec.md) sección por sección.

### 6. Refresh automático (opcional)

Requiere **Power BI Pro** y un **on-premises data gateway** (porque Postgres está en local).

1. Publicar: `File → Publish → My workspace` (app.powerbi.com)
2. En el workspace: `Settings → Dataset → Scheduled refresh`
3. Configurar cada 30 min (más lento que Airflow horario, alineado con los marts).

Si no tienes Pro: refrescar manualmente con `Ctrl+R` en Desktop.

## Archivos en este folder

| Archivo | Propósito |
|---------|-----------|
| `queries.m` | Power Query M para las 6 tablas del modelo |
| `measures.dax` | ~30 medidas DAX listas para pegar |
| `layout_spec.md` | Especificación visual página por página |
| `README.md` | Este archivo |

> Nota: el binario `.pbix` NO se versiona en git (ver `.gitignore`). Si lo compartes con un colega, expórtalo como `.pbit` (File → Export → Power BI template).

## Troubleshooting

### "The expression 'DateTime.AddZone' requires a value of type Zone"
La query `PriceHourly` filtra por los últimos 14 días con zona horaria. Si tu instancia de Postgres devuelve `timestamp without time zone`, cambiar `DateTime.AddZone(..., 0)` por `DateTime.LocalNow() - #duration(14, 0, 0, 0)` y el tipo de columna `ts_hour` a `datetime`.

### "PostgreSQL: no se pudo conectar al servidor"
- ¿Está `docker compose ps` mostrando `postgres` healthy?
- ¿El firewall de Windows permite la conexión a `localhost:5432`?
- Si es la primera vez, habilita "Encryption: disabled" en el diálogo de autenticación.

### Queries vacías después del refresh
Correr `make silver-e2e gold-ml-e2e` al menos una vez. Las vistas `bi.*` dependen de los marts de dbt.

### Relación rechazada por tipo
Power BI no deja relacionar `datetimezone` con `date` directamente. Agregar columna calculada:
```dax
date = DATE(YEAR([ts_hour]), MONTH([ts_hour]), DAY([ts_hour]))
```
Y crear la relación desde esa.

## Próximas mejoras

- Añadir tabla `bi.v_coin_performance_30d` para comparativa YoY cuando haya historia.
- Drill-through desde anomalies → price detail con filtro `symbol + rango temporal`.
- Theme file `theme.json` con paleta consistente.
- Exportar snapshots diarios a PDF via Power BI Service (requiere Pro).
