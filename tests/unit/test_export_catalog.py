"""Invariantes del catálogo exportado para agent-core (espejo de agent_core.views.classification.FieldRule)."""

from __future__ import annotations

import re

from pipeline.export_catalog import FIELD_CLASSES, build

TAG = re.compile(r"^[a-z]{1,12}$")


def test_every_rule_is_valid_for_agent_core() -> None:
    catalog = build()
    assert catalog
    for path, rule in catalog.items():
        assert rule["field_class"] in FIELD_CLASSES, path
        if rule["field_class"] == "pii_direct":
            assert TAG.match(rule["tag"]), path
        if rule["field_class"] == "pii_quasi":
            assert rule["quasi"]["op"] in {"drop", "age_bucket"}, path
            assert rule["quasi"]["width"] > 0, path
        else:
            assert "quasi" not in rule, f"{path}: quasi solo aplica a pii_quasi"


def test_known_pii_is_classified_and_untrusted_text_is_wrapped() -> None:
    c = build()
    assert c["customer_profile.first_name"] == {"field_class": "pii_direct", "tag": "name"}
    assert c["customer_profile.date_of_birth"]["quasi"] == {"op": "age_bucket", "width": 10}
    assert c["customer_cases.complaint_description"]["field_class"] == "untrusted_text"
    assert c["turns.text"]["field_class"] == "untrusted_text"


def test_no_direct_pii_is_exported_as_public() -> None:
    c = build()
    for field in ("document_number", "email", "mobile_phone", "address", "first_name", "last_name"):
        assert c[field]["field_class"] == "pii_direct", field
