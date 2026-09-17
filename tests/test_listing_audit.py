"""Tests for listing_audit and aeo_listing."""

from __future__ import annotations

import pandas as pd
import pytest

import aeo_listing
import listing_audit


def _unit(**overrides) -> dict:
    row = {
        "VINSerialNumber": "TEST123",
        "Year": 2015,
        "Manufacturer": "JOHN DEERE",
        "Model": "710J",
        "Category": "Loader Backhoes",
        "SaleListPrice": 61500,
        "LocationCity": "La Porte City",
        "LocationState": "Iowa",
        "LocationPostalCode": "50651",
        "LocationCountry": "US",
        "PictureCount": 15,
        "Description": "Full cab heat/AC, ExtendaHoe, 4x4",
        "DisplayName": "",
        "hours": 4137,
        "horsepower": 126,
        "cab": "",
        "cabair": "",
        "drive": "4WD",
        "extendahoe": 1,
    }
    row.update(overrides)
    return row


def _frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# --------------------------------------------------------------------------- #
# is_blank
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", [None, "", "   ", "nan", "None", float("nan")])
def test_is_blank_true(value):
    assert listing_audit.is_blank(value)


@pytest.mark.parametrize("value", [0, "0", 1, "Yes", "4WD", 0.0])
def test_is_blank_false_for_real_values(value):
    """Zero is information ("no thumb"), not a missing value."""
    assert not listing_audit.is_blank(value)


# --------------------------------------------------------------------------- #
# Check 1 -- filter exclusion
# --------------------------------------------------------------------------- #

def test_flags_cab_claimed_in_text_but_field_blank():
    found = listing_audit.find_filter_exclusions(_frame(_unit()))
    assert set(found["feature"]) >= {"cab", "cab A/C"}
    assert (found["serial"] == "TEST123").all()


def test_no_flag_when_field_is_populated():
    found = listing_audit.find_filter_exclusions(
        _frame(_unit(cab="Enclosed", cabair=1))
    )
    assert "cab" not in set(found["feature"])


def test_no_flag_when_feature_not_claimed():
    found = listing_audit.find_filter_exclusions(
        _frame(_unit(Description="Runs good", cab="", cabair=""))
    )
    assert found.empty


def test_any_populated_alternate_field_clears_the_flag():
    """PTO lives in both `haspto` and `pto`; either one is enough."""
    rows = _frame(_unit(Description="1000 PTO", haspto=1, pto=""))
    assert "PTO" not in set(listing_audit.find_filter_exclusions(rows)["feature"])


def test_drive_claimed_as_4x4_but_blank_is_flagged():
    found = listing_audit.find_filter_exclusions(
        _frame(_unit(Description="4x4, runs good", drive="", cab="x", cabair="x"))
    )
    assert "4WD/drive" in set(found["feature"])


# --------------------------------------------------------------------------- #
# Check 2 -- completeness
# --------------------------------------------------------------------------- #

def test_completeness_full_score():
    scored = listing_audit.score_completeness(_frame(_unit()))
    assert scored["score"].iloc[0] == len(listing_audit.COMPLETENESS_FIELDS)


def test_photos_below_threshold_costs_a_point():
    scored = listing_audit.score_completeness(_frame(_unit(PictureCount=2)))
    assert not scored["photos"].iloc[0]
    assert scored["score"].iloc[0] == len(listing_audit.COMPLETENESS_FIELDS) - 1


def test_usage_satisfied_by_mileage_when_hours_missing():
    scored = listing_audit.score_completeness(
        _frame(_unit(hours="", mileage=80000))
    )
    assert scored["usage"].iloc[0]


def test_missing_usage_is_detected():
    scored = listing_audit.score_completeness(_frame(_unit(hours="", mileage="")))
    assert not scored["usage"].iloc[0]


# --------------------------------------------------------------------------- #
# Check 3 -- webstats join
# --------------------------------------------------------------------------- #

def _stats(**overrides) -> dict:
    row = {
        "SerialNumber": "TEST123",
        "DetailsViews": 112,
        "DailyDetailViews": 3.73,
        "Impressions": 4503,
        "ClickThroughRate": "2.49%",
        "TotalWatchlists": 5,
        "TotalClicksToCall": 0,
        "EmailLeads": 0,
        "DaysAging": 198,
    }
    row.update(overrides)
    return row


def test_join_matches_on_serial_case_insensitively():
    merged = listing_audit.join_webstats(
        _frame(_unit()), _frame(_stats(SerialNumber=" test123 "))
    )
    assert len(merged) == 1
    assert merged["DaysAging"].iloc[0] == 198


def test_join_parses_percentage_ctr():
    merged = listing_audit.join_webstats(_frame(_unit()), _frame(_stats()))
    assert merged["ctr"].iloc[0] == pytest.approx(2.49)


def test_blank_serials_never_cross_match():
    """Two unnumbered rows must not join to each other and fan the result out."""
    merged = listing_audit.join_webstats(
        _frame(_unit(VINSerialNumber="")), _frame(_stats(SerialNumber=""))
    )
    assert merged.empty


def test_relisted_serial_keeps_the_best_performing_row():
    merged = listing_audit.join_webstats(
        _frame(_unit()),
        _frame(_stats(DetailsViews=5), _stats(DetailsViews=400)),
    )
    assert len(merged) == 1
    assert merged["DetailsViews"].iloc[0] == 400


def test_triage_scores_and_orders_units():
    merged = listing_audit.join_webstats(
        _frame(_unit(), _unit(VINSerialNumber="OTHER1")),
        _frame(_stats(), _stats(SerialNumber="OTHER1", DailyDetailViews=9.0,
                                DaysAging=10)),
    )
    ranked = listing_audit.triage(merged)
    assert ranked["demand_score"].is_monotonic_decreasing
    assert ranked["serial" if "serial" in ranked else "VINSerialNumber"].iloc[0] == "OTHER1"


# --------------------------------------------------------------------------- #
# AEO builder
# --------------------------------------------------------------------------- #

def test_find_unit_is_case_insensitive():
    unit = aeo_listing.find_unit(_frame(_unit()), "test123")
    assert unit["Model"] == "710J"


def test_find_unit_raises_on_unknown_serial():
    with pytest.raises(KeyError):
        aeo_listing.find_unit(_frame(_unit()), "NOPE")


def test_unit_name_reads_like_a_search_query():
    assert aeo_listing.unit_name(_frame(_unit()).iloc[0]) == "2015 JOHN DEERE 710J"


def test_jsonld_carries_serial_and_offer():
    product = aeo_listing.build_jsonld(_frame(_unit()).iloc[0])
    assert product["@type"] == "IndividualProduct"
    assert product["serialNumber"] == "TEST123"
    assert product["offers"]["price"] == 61500
    assert product["offers"]["_closeProcess"]["acceptsAgentInitiatedPurchase"] is False


def test_jsonld_emits_first_party_gaps_as_explicit_nulls():
    """Lien and inspection have no Sandhills column; never silently omit them."""
    product = aeo_listing.build_jsonld(_frame(_unit()).iloc[0])
    pending = {
        p["name"]: p for p in product["additionalProperty"] if "_pending" in p
    }
    assert set(pending) == set(aeo_listing.FIRST_PARTY_ONLY)
    assert all(p["value"] is None for p in pending.values())


def test_jsonld_never_invents_a_missing_value():
    product = aeo_listing.build_jsonld(
        _frame(_unit(hours="", horsepower="")).iloc[0]
    )
    names = [p["name"] for p in product["additionalProperty"]]
    assert "engineHours" not in names
    assert "horsepower" not in names


def test_faq_reports_an_inaccurate_hour_meter():
    faq = aeo_listing.build_faq(_frame(_unit(hoursmeterinaccurate="true")).iloc[0])
    hours_answer = next(a for q, a in faq if "hours are on" in q)
    assert "inaccurate" in hours_answer


def test_faq_discloses_a_rebuilt_title():
    faq = aeo_listing.build_faq(_frame(_unit(rebuilttitle="true")).iloc[0])
    title_answer = next(a for q, a in faq if "clean title" in q)
    assert "rebuilt" in title_answer.lower()


def test_faq_states_agents_may_quote_but_not_buy():
    faq = aeo_listing.build_faq(_frame(_unit()).iloc[0])
    agent_answer = next(a for q, a in faq if "AI agent" in q)
    assert "quote" in agent_answer and "human signature" in agent_answer


def test_faq_falls_back_to_mileage_for_a_truck():
    faq = aeo_listing.build_faq(
        _frame(_unit(hours="", mileage=80000, mileagetype="miles")).iloc[0]
    )
    assert any("mileage" in q.lower() for q, _ in faq)


def test_faq_jsonld_is_a_faqpage():
    faq = aeo_listing.build_faq(_frame(_unit()).iloc[0])
    doc = aeo_listing.faq_jsonld(faq)
    assert doc["@type"] == "FAQPage"
    assert len(doc["mainEntity"]) == len(faq)
    assert doc["mainEntity"][0]["acceptedAnswer"]["@type"] == "Answer"


def test_markdown_names_the_unpublished_trust_fields():
    unit = _frame(_unit()).iloc[0]
    page = aeo_listing.render_markdown(unit, aeo_listing.build_faq(unit))
    assert "lienStatus" in page and "inspectionReport" in page
