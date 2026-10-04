"""Perfilado puntual de interactions y call_transcripts en silver (diagnóstico, no forma parte del pipeline)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
con = duckdb.connect(str(Path(os.environ.get("PIPELINE_ROOT", ROOT / "data")) / "warehouse.duckdb"), read_only=True)


def q(sql: str):
    return con.execute(sql).fetchall()


print("cuarentena:", q("select table_name, outcome, rows from gold_analytics.dq_quarantine where table_name in ('interactions','call_transcripts') order by 1,2"))
print("interactions silver:", q("select count(*) from silver.interactions")[0][0], "| transcripts silver:", q("select count(*) from silver.call_transcripts")[0][0])
print("transcripts por interacción (max):", q("select max(n) from (select count(*) n from silver.call_transcripts group by interaction_id)")[0][0])
print("has_transcript vs transcripción real:", q("select i.has_transcript, t.interaction_id is not null, count(*) from silver.interactions i left join silver.call_transcripts t using(interaction_id) group by 1,2 order by 1,2"))
print("idioma transcripciones:", q("select detected_language, count(*) from silver.call_transcripts group by 1"))
print("--- nulos por canal (% nulo)")
for col in ("duration_seconds", "wait_time_seconds", "customer_detected_accent", "agent_used_accent", "mentioned_products", "detected_sentiment", "sentiment_score"):
    print(col, q(f"select channel, round(100.0*avg(case when {col} is null then 1 else 0 end),1) from silver.interactions group by 1 order by 1"))
print("--- nulos por interaction_type (wait_time, duration)")
print(q("select interaction_type, round(100.0*avg(case when wait_time_seconds is null then 1 else 0 end),1), round(100.0*avg(case when duration_seconds is null then 1 else 0 end),1), count(*) from silver.interactions group by 1 order by 1"))
print("agent_id nulo:", q("select count(*) from silver.interactions where agent_id is null")[0][0])
print("canal x tipo:", q("select channel, interaction_type, count(*) from silver.interactions group by 1,2 order by 3 desc"))
print("fechas desplazadas (huso):", q("select is_partition_date_shifted, count(*) from silver.interactions group by 1"))
print("--- transcripts: nulos y contenido")
for col in ("detected_accent", "accent_confidence", "detected_keywords", "mentioned_entities", "detected_intents", "audio_quality", "duration_seconds"):
    print(col, q(f"select round(100.0*avg(case when {col} is null then 1 else 0 end),1) from silver.call_transcripts")[0][0])
print("textos distintos (cliente/agente):", q("select count(distinct customer_text), count(distinct agent_text) from silver.call_transcripts"))
print("mentioned_entities ejemplo:", q("select mentioned_entities from silver.call_transcripts where mentioned_entities is not null limit 2"))
print("detected_intents:", q("select detected_intents, count(*) from silver.call_transcripts group by 1 order by 2 desc limit 5"))
print("placeholders sin rellenar ({...}):", q("select count(*) from silver.call_transcripts where regexp_matches(full_text, '[{][A-Za-z_]+[}]')")[0][0])
print("--- canónico")
print("cases por fuente:", q("select source_system, count(*) from canonical.cases group by 1 order by 1"))
print("case_closes por fuente:", q("select source_system, count(*) from canonical.case_closes group by 1 order by 1"))
print("routing por fuente/outcome:", q("select source_system, outcome, count(*) from canonical.routing_steps group by 1,2 order by 1,2"))
print("canal canónico (interacciones):", q("select channel, origin, count(*) from canonical.cases where source_system='bank_interactions' group by 1,2 order by 3 desc"))
