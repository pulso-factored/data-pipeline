"""Genera dbt/seeds/null_policy.csv a partir de las columnas silver con nulos y las reglas verificadas
en el perfilado (docs/01-hallazgos-de-calidad.md). Las columnas con nulos y SIN regla se listan al final:
hay que clasificarlas a mano (el test dq_unexplained_nulls también las detecta)."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("PIPELINE_ROOT", ROOT / "data")) / "warehouse.duckdb"

# (tabla, columna) -> (tipo, nota). Tipos: structural | state | derivable | missing_real | not_in_source
RULES: dict[tuple[str, str], tuple[str, str]] = {
    # customers: opcionales en el diccionario; faltantes reales, nunca se imputan
    **{("customers", c): ("missing_real", "Opcional en el diccionario. No se imputa; is_missing_* lo expone.")
       for c in ["email", "mobile_phone", "landline_phone", "address", "postal_code", "detected_accent",
                 "credit_score", "estimated_monthly_income", "occupation", "marital_status", "education_level"]},
    # products
    ("products", "credit_limit"): ("structural", "Solo aplica a tarjeta de crédito y préstamos; dentro de lo aplicable ~5% es faltante real (is_missing_credit_limit)."),
    ("products", "days_past_due"): ("structural", "Solo aplica a créditos."),
    ("products", "expiration_date"): ("structural", "Solo productos a plazo."),
    ("products", "interest_rate"): ("missing_real", "~10% sin tasa."),
    ("products", "last_transaction_date"): ("state", "Producto sin movimientos todavía."),
    # complaints
    ("complaints", "subcategory"): ("missing_real", "~10% sin subcategoría."),
    ("complaints", "affected_product_id"): ("missing_real", "Reclamo sin producto asociado."),
    ("complaints", "related_branch_id"): ("missing_real", "Reclamo sin sucursal."),
    ("complaints", "origin_interaction_id"): ("not_in_source", "100% vacío en el origen: no se puede enlazar llamada y reclamo."),
    ("complaints", "claimed_amount"): ("missing_real", "Monto reclamado opcional."),
    ("complaints", "currency"): ("missing_real", "Va con claimed_amount."),
    **{("complaints", c): ("state", "Aún no ocurrió (caso abierto o sin asignar).")
       for c in ["assigned_agent_id", "assignment_date", "first_response_date", "resolution_date", "closing_date",
                 "resolution_days", "resolution", "compensation_granted", "resolution_satisfaction"]},
    # transactions
    **{("transactions", c): ("structural", "Solo purchase y payment; ~5% faltante real dentro de lo aplicable.")
       for c in ["transaction_category", "merchant_name", "merchant_category"]},
    ("transactions", "branch_id"): ("structural", "Solo atm y branch; ~5% faltante real dentro de lo aplicable."),
    ("transactions", "latitude"): ("structural", "Solo atm, branch y pos; ~71% faltante real dentro de lo aplicable."),
    ("transactions", "longitude"): ("structural", "Solo atm, branch y pos; ~71% faltante real dentro de lo aplicable."),
    ("transactions", "fraud_score"): ("missing_real", "~20% uniforme."),
    ("transactions", "transaction_city"): ("missing_real", "~10%."),
    ("transactions", "response_code"): ("missing_real", "~5%."),
    # interactions: duración y espera dependen del tipo de contacto
    ("interactions", "duration_seconds"): ("structural", "Solo llamadas y video; chat y email no tienen duración (0% faltante dentro de lo aplicable)."),
    ("interactions", "wait_time_seconds"): ("structural", "Solo llamadas entrantes (0% faltante dentro de lo aplicable)."),
    ("interactions", "customer_detected_accent"): ("missing_real", "~30% uniforme en todos los canales."),
    ("interactions", "agent_used_accent"): ("missing_real", "~30% uniforme en todos los canales."),
    ("interactions", "mentioned_products"): ("missing_real", "~60%; la ausencia puede significar que no se mencionó ningún producto."),
    # call_transcripts: 42 plantillas con marcadores sin rellenar; la intención detectada es siempre consulta_general
    **{("call_transcripts", c): ("missing_real", "Metadato del transcriptor opcional.")
       for c in ["detected_accent", "accent_confidence", "detected_keywords", "mentioned_entities", "detected_intents",
                 "audio_quality", "duration_seconds"]},
    # satisfaction_surveys
    ("satisfaction_surveys", "nps_category"): ("structural", "Solo las encuestas NPS; ~5% faltante real dentro de NPS."),
    **{("satisfaction_surveys", c): ("missing_real", "Pregunta/comentario opcional (~43% / ~62% / ~81% sin responder; 13 comentarios distintos).")
       for c in ["question_1_text", "question_1_response", "question_2_text", "question_2_response", "question_3_text",
                 "question_3_response", "open_comments", "comment_sentiment", "campaign_response_rate"]},
    # campaign_sends
    ("campaign_sends", "was_opened"): ("structural", "Solo Email, Push y SMS entregados: Voice y WhatsApp no rastrean aperturas y un envío no entregado no puede abrirse."),
    **{("campaign_sends", c): ("state", "Solo existe si el evento ocurrió (abrió, hizo clic, convirtió).")
       for c in ["open_ts", "click_ts", "click_count", "conversion_ts", "conversion_value"]},
    **{("campaign_sends", c): ("state", "Solo existe si el correo se abrió; ~10% faltante real dentro de lo abierto.")
       for c in ["open_device", "open_country"]},
    ("campaign_sends", "failure_reason"): ("structural", "Solo envíos no exitosos (Failed, Bounced, Blocked); ~5% faltante real dentro de ellos."),
    ("campaign_sends", "subject"): ("structural", "Solo Email; ~10% faltante real dentro de Email."),
    ("campaign_sends", "template_used"): ("missing_real", "~10%."),
    ("campaign_sends", "send_cost"): ("missing_real", "~15% uniforme en todos los canales (is_missing_send_cost)."),
    # digital_events
    ("digital_events", "customer_id"): ("derivable", "24% de los eventos: 3,1 M están en sesiones totalmente anónimas (20% de las sesiones, sin cliente) y 624 mil en sesiones mixtas, donde se derivan del cliente único de la sesión (customer_id_resolved / customer_id_source)."),
    ("digital_events", "customer_id_resolved"): ("structural", "Sesión totalmente anónima (20% de las sesiones, 3,1 M de eventos): no hay cliente que derivar."),
    ("digital_events", "duration_seconds"): ("structural", "Solo PageView; ~5% faltante real dentro de PageView."),
    ("digital_events", "event_value"): ("structural", "Solo FormSubmit y Purchase; ~5% faltante real dentro de ellos."),
    ("digital_events", "product_id"): ("structural", "Solo eventos ligados a un producto (Click ~19%, PageView ~13%)."),
    ("digital_events", "browser"): ("structural", "Solo canales web; ~5% faltante real dentro de ellos."),
    ("digital_events", "app_version"): ("structural", "Solo apps; ~5% faltante real dentro de ellas."),
    **{("digital_events", c): ("missing_real", "Opcional; faltante uniforme entre tipos de evento.")
       for c in ["platform", "page_url", "page_title", "action", "element_id", "ip_address", "ip_city"]},
    **{("digital_events", c): ("missing_real", "Atribución de marketing: ~93-95% sin dato.")
       for c in ["referrer", "utm_source", "utm_medium", "utm_campaign"]},
    # marketing_campaigns
    **{("marketing_campaigns", c): ("missing_real", "Opcional en el diccionario.")
       for c in ["description", "promoted_product", "target_segment", "target_country", "budget", "expected_conversion_rate"]},
    # service_agents
    **{("service_agents", c): ("missing_real", "Opcional en el diccionario.")
       for c in ["phone", "assigned_branch_id", "specialty", "avg_csat", "total_monthly_interactions"]},
    ("transactions", "amount_usd_reported"): ("derivable", "Se completa en amount_usd (identidad para USD, tasa del día para COP/ARS); ver amount_usd_source."),
}

TABLES = ["customers", "products", "complaints", "transactions", "interactions", "call_transcripts", "service_agents", "satisfaction_surveys", "campaign_sends", "digital_events", "marketing_campaigns"]


def main() -> None:
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    rows, unexplained = [], []
    for t in TABLES:
        cols = [r[0] for r in con.execute(f"describe silver.{t}").fetchall() if not r[0].startswith("_")]
        for c in cols:
            nulls = con.execute(f'select count(*) - count("{c}") from silver.{t}').fetchone()[0]
            if nulls == 0:
                continue
            rule = RULES.get((t, c))
            if rule is None:
                unexplained.append((t, c, nulls))
                continue
            rows.append((t, c, rule[0], rule[1]))
    out = ROOT / "dbt" / "seeds" / "null_policy.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table_name", "column_name", "null_type", "note"])
        w.writerows(rows)
    print(f"{len(rows)} reglas escritas en {out}")
    if unexplained:
        print("COLUMNAS CON NULOS SIN REGLA:", unexplained)


if __name__ == "__main__":
    main()
