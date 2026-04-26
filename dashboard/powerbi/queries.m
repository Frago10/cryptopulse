// =============================================================================
// queries.m — Power Query (M) scripts para CryptoPulse
// =============================================================================
// Instrucciones:
//   1. En Power BI Desktop: Get Data -> PostgreSQL database
//        Server:   localhost:5432         (o la IP de tu Docker host)
//        Database: cryptopulse
//        Data Connectivity: Import  (no DirectQuery — ver README)
//   2. Para cada tabla de abajo: Home -> New Source -> Blank Query
//      -> Advanced Editor -> pegar el snippet.
//   3. Nombrar la query segun el comentario de cabecera.
//   4. Close & Apply.
//
// Autenticacion:
//   Database -> Username: cryptopulse / Password: <tu POSTGRES_PASSWORD>
//   Encryption: disabled (conexion local). En prod usar SSH tunnel.
//
// Refresh: programar refresh automatico en Power BI Service cada 30 min
//   (basta con que sea mas lento que la corrida horaria de Airflow).
// =============================================================================


// ------------------------------------------------------------
// Query name: KPI_Latest
// Card row + executive summary. Una sola fila.
// ------------------------------------------------------------
let
    Source = PostgreSQL.Database("localhost", "cryptopulse"),
    bi_v_kpi_latest = Source{[Schema="bi", Item="v_kpi_latest"]}[Data]
in
    bi_v_kpi_latest


// ------------------------------------------------------------
// Query name: PriceHourly
// Time-series OHLCV por hora por simbolo.
// Recorta a los ultimos 14 dias para que el modelo no se hinche.
// ------------------------------------------------------------
let
    Source = PostgreSQL.Database("localhost", "cryptopulse"),
    v_price_hourly = Source{[Schema="bi", Item="v_price_hourly"]}[Data],
    FilteredRecent = Table.SelectRows(
        v_price_hourly,
        each [ts_hour] >= DateTime.AddZone(
                            DateTime.LocalNow() - #duration(14, 0, 0, 0),
                            0)
    ),
    TypedReturn = Table.TransformColumnTypes(
        FilteredRecent,
        {
            {"ts_hour",         type datetimezone},
            {"price_open",      type number},
            {"price_high",      type number},
            {"price_low",       type number},
            {"price_close",     type number},
            {"price_vwap",      type number},
            {"hour_return_pct", type number},
            {"ticks_count",     Int64.Type}
        }
    )
in
    TypedReturn


// ------------------------------------------------------------
// Query name: AnomalyAlerts
// Alertas de anomalia con severidad y detector.
// ------------------------------------------------------------
let
    Source = PostgreSQL.Database("localhost", "cryptopulse"),
    v_anomaly_alerts = Source{[Schema="bi", Item="v_anomaly_alerts"]}[Data],
    Typed = Table.TransformColumnTypes(
        v_anomaly_alerts,
        {
            {"ts_hour",          type datetimezone},
            {"price_close",      type number},
            {"hour_return_pct",  type number},
            {"return_zscore",    type number},
            {"severity",         type number},
            {"fng_value",        Int64.Type},
            {"reddit_mentions_day", Int64.Type}
        }
    )
in
    Typed


// ------------------------------------------------------------
// Query name: SentimentDaily
// Fear&Greed + VADER por dia.
// ------------------------------------------------------------
let
    Source = PostgreSQL.Database("localhost", "cryptopulse"),
    v_sentiment_daily = Source{[Schema="bi", Item="v_sentiment_daily"]}[Data],
    Typed = Table.TransformColumnTypes(
        v_sentiment_daily,
        {
            {"date_day",            type date},
            {"fng_value",           Int64.Type},
            {"vader_compound_avg",  type number},
            {"vader_pct_positive",  type number},
            {"vader_pct_negative",  type number},
            {"reddit_posts_count",  Int64.Type},
            {"vader_posts_count",   Int64.Type}
        }
    )
in
    Typed


// ------------------------------------------------------------
// Query name: MarketSnapshot
// Un row por coin con el snapshot mas reciente de CoinGecko.
// ------------------------------------------------------------
let
    Source = PostgreSQL.Database("localhost", "cryptopulse"),
    v_market_snapshot_latest = Source{[Schema="bi",
                                       Item="v_market_snapshot_latest"]}[Data],
    Typed = Table.TransformColumnTypes(
        v_market_snapshot_latest,
        {
            {"price",          type number},
            {"market_cap",     type number},
            {"market_cap_rank", Int64.Type},
            {"volume_24h",     type number},
            {"change_24h_pct", type number},
            {"change_7d_pct",  type number},
            {"change_1h_pct",  type number},
            {"as_of",          type datetimezone}
        }
    )
in
    Typed


// ------------------------------------------------------------
// Query name: DateDim
// Dimension de tiempo para relacionar los facts. Genera 3 anios de fechas.
// Power BI la usa como "Mark as date table" para time intelligence (YTD, MoM).
// ------------------------------------------------------------
let
    StartDate  = #date(2025, 1, 1),
    EndDate    = Date.From(DateTime.LocalNow()) + #duration(30, 0, 0, 0),
    NumDays    = Duration.Days(EndDate - StartDate),
    DateList   = List.Dates(StartDate, NumDays, #duration(1, 0, 0, 0)),
    AsTable    = Table.FromList(DateList, Splitter.SplitByNothing(),
                                {"date"}, null, ExtraValues.Error),
    Typed      = Table.TransformColumnTypes(AsTable, {{"date", type date}}),
    Enriched   = Table.AddColumn(Typed, "year",    each Date.Year([date]),    Int64.Type),
    Enriched2  = Table.AddColumn(Enriched, "month", each Date.Month([date]),   Int64.Type),
    Enriched3  = Table.AddColumn(Enriched2, "day",  each Date.Day([date]),     Int64.Type),
    Enriched4  = Table.AddColumn(Enriched3, "weekday", each Date.DayOfWeekName([date]), type text),
    Enriched5  = Table.AddColumn(Enriched4, "year_month",
                                  each Text.From(Date.Year([date])) & "-" &
                                       Text.PadStart(Text.From(Date.Month([date])), 2, "0"),
                                  type text)
in
    Enriched5
