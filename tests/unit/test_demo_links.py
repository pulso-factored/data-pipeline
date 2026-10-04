"""Selección determinista de vínculos plataforma -> dataset. Candidatos sintéticos: no usa datos del reto."""

from __future__ import annotations

import pytest

from pipeline.demo_links import Candidate, LinkError, parse_platform_seed, select_links


def _c(cid: str, country: str = "CO", products: int = 1, tx: int = 50, e0: int = 1, pt: int = 0, dig: int = 0) -> Candidate:
    return Candidate(cid, country, products, tx, e0, pt, dig)


PLATFORM = {
    "CUS-1": {"country": "CO", "locale": "es-CO"},
    "CUS-2": {"country": "MX", "locale": "es-MX"},
    "CUS-3": {"country": "AR", "locale": "pt-BR"},
}


def _pool() -> list[Candidate]:
    return (
        [_c(f"CO{i}", "CO") for i in range(5)]
        + [_c(f"MX{i}", "MX") for i in range(5)]
        + [_c("AR-PT", "AR", pt=1), _c("CO-PT", "CO", pt=1)]
    )


def test_links_match_country_and_language_and_never_repeat_a_dataset_customer() -> None:
    links, report = select_links(PLATFORM, _pool())
    assert links["CUS-1"].startswith("CO") and links["CUS-2"].startswith("MX")
    assert links["CUS-3"] == "AR-PT"  # portugués: solo clientes con un caso pt de E0, y del mismo país si hay
    assert len(set(links.values())) == len(links)
    assert all(r["country_matches"] for r in report)


def test_selection_is_deterministic_and_independent_of_input_order() -> None:
    a, _ = select_links(PLATFORM, _pool())
    b, _ = select_links(dict(reversed(list(PLATFORM.items()))), list(reversed(_pool())))
    assert a == b


def test_a_poor_customer_is_never_linked() -> None:
    pool = [_c("RICH", "CO"), _c("NO_PRODUCT", "CO", products=0), _c("FEW_TX", "CO", tx=3)]
    links, _ = select_links({"CUS-1": {"country": "CO", "locale": "es-CO"}}, pool)
    assert links["CUS-1"] == "RICH"


def test_customers_with_a_dispute_are_preferred_but_not_required() -> None:
    pool = [_c("NO_E0", "CO", e0=0), _c("WITH_E0", "CO", e0=2)]
    one, _ = select_links({"CUS-1": {"country": "CO", "locale": "es-CO"}}, pool)
    assert one["CUS-1"] == "WITH_E0"
    two, _ = select_links({"CUS-1": {"country": "CO", "locale": "es-CO"}, "CUS-2": {"country": "CO", "locale": "es-CO"}}, pool)
    assert set(two.values()) == {"NO_E0", "WITH_E0"}  # el segundo cae al grupo sin disputa en vez de fallar


def test_not_enough_candidates_fails_loudly_instead_of_linking_a_poor_customer() -> None:
    with pytest.raises(LinkError, match="CUS-3"):
        select_links(PLATFORM, [_c("CO0", "CO"), _c("MX0", "MX")])  # nadie con caso en portugués


def test_the_report_carries_ids_and_counts_but_no_personal_data() -> None:
    _, report = select_links({"CUS-1": {"country": "CO", "locale": "es-CO"}}, [_c("CO0", "CO", dig=4)])
    assert set(report[0]) == {
        "platform_customer", "dataset_customer", "wanted", "dataset_country", "country_matches", "language_note",
        "active_core_products", "transactions", "e0_cases", "e0_pt_cases", "digital_sessions_90d",
    }


def test_the_platform_seed_parser_reads_ids_country_and_language_but_not_names() -> None:
    seed = '''
    CustomerSeed(1001, "Marcela Quintana Pardo", ES_CO, "Barranquilla", CO, suggestions=("x",)),
    CustomerSeed(2004, "Rafael Nogueira Costa", PT_BR, "Buenos Aires", AR, simulator=True),
    '''
    parsed = parse_platform_seed(seed)
    assert parsed == {
        "CUS-00000000000000000000001001": {"country": "CO", "locale": "es-CO"},
        "CUS-00000000000000000000002004": {"country": "AR", "locale": "pt-BR"},
    }
    assert "Marcela" not in str(parsed)
