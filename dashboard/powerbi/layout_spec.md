# CryptoPulse — Power BI Layout Spec

Este documento describe cómo montar el `.pbix` página por página. El archivo binario `.pbix` no vive en git (ver `.gitignore`): si lo necesitas compartir, sube sólo el `.pbit` (template) al repo.

---

## Modelo de datos (Power BI Model view)

### Tablas (por queries.m)

| Tabla | Rol | Granularidad |
|-------|-----|--------------|
| `KPI_Latest` | Hub de métricas ejecutivas | 1 fila (snapshot) |
| `PriceHourly` | Fact de precios | 1 fila por `(symbol, ts_hour)` |
| `AnomalyAlerts` | Fact de alertas | 1 fila por `(symbol, ts_hour)` marcada anómala |
| `SentimentDaily` | Fact de sentimiento | 1 fila por `date_day` |
| `MarketSnapshot` | Fact de overview | 1 fila por `coin_id` |
| `DateDim` | Dimensión de tiempo (marcada como date table) | 1 fila por día |

### Relaciones

```
DateDim[date] 1 ─── * PriceHourly[ts_hour]           (usar CALCULATE con TREATAS si hay mismatch de tipo)
DateDim[date] 1 ─── * AnomalyAlerts[ts_hour]
DateDim[date] 1 ─── * SentimentDaily[date_day]
DateDim[date] 1 ─── * MarketSnapshot[as_of]
```

`KPI_Latest` NO se relaciona con nadie: es una tabla de 1 fila, usada sólo en tarjetas.

> **Tip**: si Power BI no deja crear la relación por el tipo `datetimezone`, añade una columna calculada `date = DATE(YEAR([ts_hour]), MONTH([ts_hour]), DAY([ts_hour]))` en cada fact y usa esa para la relación con `DateDim[date]`.

### "Mark as date table"

Selecciona `DateDim` → Table tools → **Mark as date table** → columna `date`. Esto habilita `TOTALYTD`, `SAMEPERIODLASTYEAR`, etc.

---

## Página 1 — Executive Summary

Objetivo: un pantallazo "all-up" para un stakeholder no técnico.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CryptoPulse · Executive Summary            [Stream Health: ● HEALTHY]   │
├─────────────┬─────────────┬─────────────┬─────────────┬──────────────────┤
│ Fear&Greed  │ Anomalies   │ Market Cap  │ Sentiment   │ Symbols Active   │
│    72       │  (24h)      │ Tracked     │ Reddit 24h  │    8 / 8         │
│  Greed      │    5        │  $2.12T     │   +0.18     │                  │
├─────────────┴─────────────┴─────────────┴─────────────┴──────────────────┤
│                                                                          │
│  LINE CHART — BTC & ETH Price (last 14d, normalizado base 100)           │
│                                                                          │
├─────────────────────────────────────┬────────────────────────────────────┤
│  BAR CHART — Alerts por simbolo     │  TABLE — Top movers (24h)          │
│  (ultimas 24h)                      │  Coin | Price | 24h% | 7d%         │
└─────────────────────────────────────┴────────────────────────────────────┘
                                                       Refreshed at <...>
```

### Visuales

1. **Titulo de pagina** (Text box): "CryptoPulse · Executive Summary"
2. **KPI Card — Stream Health**:
   - Valor: `[Stream_Health_Label]`
   - Color de fondo condicional: `[Stream_Health_Color]` (Format → Background → fx → Field value)
3. **KPI Cards (fila superior, 5 tarjetas)**:
   - `[Fear_Greed_Latest]` con subtitulo `[Fear_Greed_Label]`
   - `[Anomalies_24h]`
   - `[Total_Market_Cap_Formatted]`
   - `[Vader_Compound_24h]` (formato `0.00`)
   - `[Symbols_Active_24h]` con subtítulo "de 8 trackeados"
4. **Line Chart — Precios normalizados (BTC, ETH, SOL)**:
   - X-axis: `PriceHourly[ts_hour]`
   - Y-axis: medida calculada `Price_Normalized = DIVIDE(MAX(PriceHourly[price_close]), CALCULATE(MIN(PriceHourly[price_close]), ALL(PriceHourly[ts_hour]))) * 100`
   - Legend: `PriceHourly[coin_name]`
   - Slicer de simbolos arriba
5. **Bar Chart — Alertas por simbolo (24h)**:
   - Axis: `AnomalyAlerts[symbol]`
   - Value: `[Alerts_Count]`
   - Filtro de página: `AnomalyAlerts[ts_hour] is in the last 24 hours`
6. **Table — Top movers**:
   - Columnas: `coin_name`, `price`, `change_24h_pct`, `change_7d_pct`
   - Conditional formatting: `change_24h_pct` → data bars (verde positivo, rojo negativo)
   - Orden: `change_24h_pct` DESC, top 10
7. **Text box (footer)**: `[Refreshed_At_Label]`

---

## Página 2 — Price Anomalies

Objetivo: deep-dive sobre las alertas, para analistas.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Price Anomalies                          [Slicer: Symbol] [Slicer: Date]│
├──────────────────────────────────────────┬───────────────────────────────┤
│  LINE CHART — price_close + markers para │  KPI Cards                    │
│  puntos con is_anomaly_consensus = TRUE  │  - Alerts_Count               │
│                                          │  - Critical_Alerts            │
│                                          │  - Avg_Severity               │
├──────────────────────────────────────────┼───────────────────────────────┤
│  TABLE — Anomaly log                     │  DONUT — Alerts by detector   │
│  ts_hour | symbol | return% | zscore |   │  (Consensus / IForest /       │
│  severity | detector | fng | vader       │   Z-score / Both)             │
└──────────────────────────────────────────┴───────────────────────────────┘
```

### Visuales

1. **Slicers** (arriba): `AnomalyAlerts[symbol]`, `DateDim[date]` (como range)
2. **Line + Scatter combo**: precio (`PriceHourly[price_close]`) con markers superpuestos donde `AnomalyAlerts[is_anomaly_consensus] = TRUE`.
3. **KPI Cards**: `[Alerts_Count]`, `[Critical_Alerts]`, `[Avg_Severity]`
4. **Table**: todas las columnas de `AnomalyAlerts` con formato condicional en `severity` (color scale: verde < 1, amarillo 1-3, naranja 3-5, rojo >= 5).
5. **Donut chart**: `AnomalyAlerts[detector_label]` → `[Alerts_Count]`.

Drill-through: click derecho en un símbolo → "Drill through to Price Detail" (opcional, crear página oculta con filtro).

---

## Página 3 — Sentiment Tracker

Objetivo: cruce Fear & Greed + Reddit.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Sentiment Tracker                               [Slicer: Date range]    │
├──────────────────────────────────────────┬───────────────────────────────┤
│  LINE CHART — Fear & Greed (0-100)       │  LINE CHART — VADER compound  │
│  con bandas: Extreme Fear (<25),         │  (−1 a +1)                    │
│  Fear (25-45), Neutral (45-55),          │                               │
│  Greed (55-75), Extreme Greed (>75)      │                               │
├──────────────────────────────────────────┴───────────────────────────────┤
│  STACKED AREA — Reddit posts/dia por sentiment_label                     │
│  (positive verde / neutral gris / negative rojo)                         │
├──────────────────────────────────────────┬───────────────────────────────┤
│  KPI — Avg F&G periodo                   │  KPI — Posts totales          │
│  KPI — Avg VADER compound                │  KPI — % positive             │
└──────────────────────────────────────────┴───────────────────────────────┘
```

### Visuales

1. **Line — Fear & Greed**: X=`date_day`, Y=`fng_value`. Constant lines en 25, 45, 55, 75 (Analytics pane).
2. **Line — VADER compound**: X=`date_day`, Y=`vader_compound_avg`.
3. **Stacked area**: X=`date_day`, Y=`reddit_posts_count`, Legend=`vader_pct_positive/negative/neutral` (requiere unpivot en M si se quiere stacked real; alternativa: 3 líneas).
4. **KPIs**: `[Avg_Fear_Greed]`, `[Avg_Vader_Compound]`, `[Total_Reddit_Posts]`, `[Pct_Positive_Posts]`.

---

## Página 4 — Market Overview

Objetivo: vista tabular tipo CoinGecko, con sparklines.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Market Overview                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ [img] Coin   Symbol  Price    MCap    Vol24h  1h%   24h%   7d%  Spark7d │
│ [btc] Bitcoin  BTC  $68,...  $1.3T   $34B   +0.2  +2.1  +5.4  ──╱─╲──    │
│ [eth] Ethereum ETH  $3,550   $427B   $18B   +0.1  +1.8  +3.9  ──╱──╲─   │
│ [sol] Solana   SOL  $172     $78B    $4B    -0.3  +0.8  +8.1  ╱──╱─╲─   │
│ ...                                                                      │
├──────────────────────────────────────────┬───────────────────────────────┤
│  BAR — Market share (por market_cap)     │  KPIs                         │
│                                          │  - MarketCap_Filtered         │
│                                          │  - Coins_Up_24h / Down_24h    │
│                                          │  - Best / Worst Performer 24h │
└──────────────────────────────────────────┴───────────────────────────────┘
```

### Visuales

1. **Table**: columnas `image_url` (Image URL type), `coin_name`, `symbol`, `price`, `market_cap`, `volume_24h`, `change_1h_pct`, `change_24h_pct`, `change_7d_pct`.
   - Formato condicional (data bars) en `change_*_pct`.
   - `market_cap`, `volume_24h` con formato `$#,##0,,"M"` para miles de millones.
   - Sparkline de precio 7d: usar la *custom visual* "Sparkline by OKViz" o el visual nativo desde 2023 (Paint → Sparkline).
2. **Bar chart**: Axis=`coin_name`, Value=`market_cap`. Ordenado DESC.
3. **KPIs**: `[MarketCap_Filtered]`, `[Coins_Up_24h]` vs `[Coins_Down_24h]`, `[Best_Performer_24h]`, `[Worst_Performer_24h]`.

---

## Tema visual

Archivo `theme.json` (opcional, se carga desde View → Themes → Browse). Paleta sugerida:

| Elemento | Color |
|----------|-------|
| Primary  | `#6366F1` (indigo) |
| Positive | `#16A34A` |
| Negative | `#DC2626` |
| Warning  | `#F59E0B` |
| Neutral  | `#6B7280` |
| Bg page  | `#0F172A` (dark) o `#FFFFFF` (light) |

---

## Refresh & Deploy

1. **Local (desarrollo)**: `File → Refresh` en Power BI Desktop. Query timeouts: 10min.
2. **Producción** (opcional, requiere Power BI Pro):
   - Subir `.pbix` a app.powerbi.com
   - Configurar **On-premises data gateway** (Postgres es local)
   - Programar refresh cada 30 min (sincronizado pero más lento que la corrida horaria de Airflow)
3. **Alertas nativas** (Power BI Service): se pueden añadir sobre la KPI card de `[Stream_Health_Label]` para avisar cuando cambie a "STALE".

---

## Checklist de validación

Antes de entregar:

- [ ] Todas las queries refrescan sin error (Transform data → Refresh all)
- [ ] `DateDim` marcada como date table
- [ ] Relaciones creadas entre `DateDim` y los facts
- [ ] KPI cards muestran valores (no "blank")
- [ ] Page navigation funciona (botones o pestañas)
- [ ] Stream_Health_Label se pinta del color correcto
- [ ] `.pbix` exportado como `.pbit` si se va a compartir el template
