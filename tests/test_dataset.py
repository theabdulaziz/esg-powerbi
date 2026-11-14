"""Checks on the model tables that Power BI loads."""

from pathlib import Path

import pandas as pd
import pytest

M = Path(__file__).resolve().parent.parent / "data" / "model"
country = pd.read_csv(M / "dim_country.csv")
indicator = pd.read_csv(M / "dim_indicator.csv")
years = pd.read_csv(M / "dim_year.csv")
obs = pd.read_csv(M / "fact_observations.csv")
scores = pd.read_csv(M / "fact_scores.csv")
latest = pd.read_csv(M / "fact_latest.csv")


def test_dimension_keys_are_unique_and_complete():
    assert country.iso3.is_unique and len(country) == 193
    assert indicator.indicator_id.is_unique and len(indicator) == 67
    assert indicator.indicator.is_unique                      # the report slices by name
    assert list(years.year) == list(range(2000, 2020))
    assert set(indicator.pillar) == {"Environment", "Social", "Governance"}
    assert not country.region.eq("Not classified").any()


def test_every_fact_row_joins_to_its_dimensions():
    for fact in (obs, scores, latest):
        assert set(fact.iso3) <= set(country.iso3)
    for fact in (obs, latest):
        assert set(fact.indicator_id) <= set(indicator.indicator_id)
    assert set(obs.year) <= set(years.year) and set(scores.year) <= set(years.year)


def test_fact_grains_have_no_duplicates():
    assert not obs.duplicated(["iso3", "indicator_id", "year"]).any()
    assert not scores.duplicated(["iso3", "year", "pillar"]).any()
    assert not latest.duplicated(["iso3", "indicator_id"]).any()


def test_carry_forward_is_flagged_and_limited_to_five_years():
    gap = obs.year - obs.reported_year
    assert gap.between(0, 5).all()
    assert ((gap > 0) == (obs.is_carried_forward == 1)).all()


def test_context_indicators_are_never_scored():
    context = set(indicator.loc[~indicator.in_score, "indicator_id"])
    assert obs.loc[obs.indicator_id.isin(context), "score"].isna().all()
    assert indicator.in_score.sum() == 43


def test_scores_are_percentiles_pointing_the_right_way():
    assert obs.score.dropna().between(0, 100).all()
    co2 = obs[(obs.indicator_id == "EN.ATM.CO2E.PC") & (obs.year == 2015)]
    assert co2.loc[co2.value.idxmax(), "score"] == 0          # highest emitter scores worst
    assert co2.loc[co2.value.idxmin(), "score"] == 100
    life = obs[(obs.indicator_id == "SP.DYN.LE00.IN") & (obs.year == 2015)]
    assert life.loc[life.value.idxmax(), "score"] == 100      # longest life scores best


def test_pillar_scores_are_the_average_of_their_indicator_scores():
    merged = obs.dropna(subset=["score"]).merge(indicator[["indicator_id", "pillar"]], on="indicator_id")
    recomputed = merged.groupby(["iso3", "year", "pillar"]).score.mean().round(2).rename("recomputed").reset_index()
    check = scores[scores.pillar != "ESG"].merge(recomputed, on=["iso3", "year", "pillar"])
    assert len(check) == (scores.pillar != "ESG").sum()
    assert (check.score - check.recomputed).abs().max() <= 0.011


def test_pillar_needs_half_its_indicators_and_esg_needs_all_three_pillars():
    pillars = scores[scores.pillar != "ESG"]
    assert (pillars.indicators_used >= 0.5 * pillars.indicators_possible).all()
    per_country_year = pillars.groupby(["iso3", "year"]).agg(n=("pillar", "size"), mean=("score", "mean")).reset_index()
    esg = scores[scores.pillar == "ESG"].merge(per_country_year, on=["iso3", "year"])
    assert (esg.n == 3).all() and len(esg) == (per_country_year.n == 3).sum()
    assert (esg.score - esg["mean"]).abs().max() <= 0.011


def test_ranks_start_at_one_and_follow_the_score():
    for (_, _), g in scores.groupby(["pillar", "year"]):
        g = g.sort_values("rank_in_year")
        assert g.rank_in_year.iloc[0] == 1
        assert g.score.is_monotonic_decreasing


def test_latest_matches_the_newest_reported_observation():
    reported = obs[obs.is_carried_forward == 0]
    newest = reported.sort_values("year").groupby(["iso3", "indicator_id"]).tail(1)
    check = latest.merge(newest, on=["iso3", "indicator_id"])
    assert len(check) == len(latest)
    assert (check.latest_year == check.year).all()
    assert (check.latest_value - check.value).abs().max() < 1e-9
    assert (latest.years_since_update == 2019 - latest.latest_year).all()


def test_headline_numbers_quoted_in_the_readme():
    assert (obs.is_carried_forward == 0).sum() == 156_606
    top = scores[(scores.pillar == "ESG") & (scores.year == 2019)].nsmallest(1, "rank_in_year").iso3.iloc[0]
    assert top == "CHE"
    usa = scores[(scores.iso3 == "USA") & (scores.year == 2019)].set_index("pillar").score
    assert usa["Governance"] == pytest.approx(82.79) and usa["Environment"] == pytest.approx(44.23)


# ------------------------------------------------- generated Power BI project
import json
import re

PROJECT = Path(__file__).resolve().parent.parent / "powerbi" / "project"
MODEL = PROJECT / "ESG Tracker.SemanticModel" / "definition"
REPORT = PROJECT / "ESG Tracker.Report" / "definition"


def model_fields() -> set[str]:
    fields = set()
    for tmdl in (MODEL / "tables").glob("*.tmdl"):
        table = tmdl.stem
        for kind, name in re.findall(r"^\t(column|measure) '?([^'=\n]+?)'?(?: =.*)?$", tmdl.read_text(encoding="utf-8"), flags=re.M):
            fields.add(f"{table}.{name.strip()}")
    return fields


def test_project_model_has_every_csv_column_and_every_measure():
    fields = model_fields()
    for table, frame in {"Country": country, "Indicator": indicator, "Years": years, "Observations": obs,
                         "Scores": scores, "Latest": latest}.items():
        assert {f"{table}.{c}" for c in frame.columns} <= fields
    dax = (PROJECT.parent / "measures.dax").read_text(encoding="utf-8")
    names = [n for n in re.findall(r"^([A-Z][A-Za-z0-9 %]*?) =", dax, flags=re.M) if not n.startswith("VAR ")]
    assert len(names) == 29 and {f"Measures.{n}" for n in names} <= fields


def test_every_field_used_by_a_visual_exists_in_the_model():
    fields = model_fields()
    visuals = list(REPORT.glob("pages/*/visuals/*/visual.json"))
    assert len(visuals) >= 30
    refs = set()
    for v in visuals:
        refs |= set(re.findall(r'"queryRef": "([^"]+)"', v.read_text(encoding="utf-8")))
    assert refs and refs <= fields, refs - fields


def test_report_has_four_pages_in_order():
    order = json.loads((REPORT / "pages" / "pages.json").read_text())["pageOrder"]
    titles = [json.loads((REPORT / "pages" / p / "page.json").read_text())["displayName"] for p in order]
    assert titles == ["Overview", "Country profile", "Compare", "Data gaps"]
