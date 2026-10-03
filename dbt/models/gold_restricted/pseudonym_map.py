"""Mapa customer_id -> seudónimo estable: HMAC-SHA256(PSEUDONYM_KEY, customer_id), 20 hex.

Vive en gold_restricted porque permite re-identificar: solo lo lee el propio pipeline para construir
gold_analytics. Se calcula en lote en Python (una función por fila dentro de DuckDB es ~100x más lenta)
y la clave nunca pasa por SQL, por target/ ni por los logs de dbt. Sin clave, el modelo falla.
Producción: la clave vive en un gestor de secretos con rotación por `kid`.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pyarrow as pa


def model(dbt, session):  # noqa: ANN001
    dbt.config(materialized="table")
    key = os.environ.get("PSEUDONYM_KEY")
    if not key:
        raise RuntimeError("PSEUDONYM_KEY no está definida: no se pueden generar seudónimos.")
    k = key.encode("utf-8")
    ids = [r[0] for r in dbt.ref("customers").project("customer_id").fetchall()]
    pseudo = [
        "cus_" + hmac.new(k, i.encode("utf-8"), hashlib.sha256).hexdigest()[:20] for i in ids
    ]
    return pa.table({"customer_id": ids, "customer_pseudo": pseudo})
