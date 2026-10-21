import copy
import math

import pytest

from pipeline.transform.category_and_score import (
    PM25_REFERENCE_UG_M3, add_category_and_score, aqi_to_category, pm25_to_score, reading_to_score,
)


@pytest.mark.parametrize("aqi,label", [
    (1, "Good"), (2, "Fair"), (3, "Moderate"), (4, "Poor"), (5, "Very Poor"),
    (1.0, "Good"), (5.0, "Very Poor"),
])
def test_every_aqi_maps_to_its_label(aqi, label):
    assert aqi_to_category(aqi) == label


@pytest.mark.parametrize("bad", [0, 6, -1, 0.999, 1.5, 4.0001, 5.0001, math.nan, math.inf,
                                 True, False, "2", None, [2], 10**400])
def test_aqi_outside_1_to_5_or_wrong_type_is_rejected(bad):
    with pytest.raises(ValueError):
        aqi_to_category(bad)


@pytest.mark.parametrize("pm,score", [
    (0, 0.0), (7.5, 50.0), (15, 100.0), (30, 200.0), (3.25, 21.666666666666668),
])
def test_score_is_percent_of_who_reference(pm, score):
    assert pm25_to_score(pm) == pytest.approx(score, rel=0, abs=1e-12)


def test_score_boundaries_around_the_reference():
    assert PM25_REFERENCE_UG_M3 == 15.0
    assert pm25_to_score(14.999) < 100 < pm25_to_score(15.001)
    assert pm25_to_score(1e-12) > 0
    assert pm25_to_score(1000) == pytest.approx(6666.666666666667)  # not capped


@pytest.mark.parametrize("bad", [-0.001, -15, math.nan, math.inf, -math.inf, True, "8.8", None, 1e308])
def test_invalid_pm25_is_rejected(bad):
    with pytest.raises(ValueError):
        pm25_to_score(bad)


def test_reading_to_score_reads_raw_and_gold_shapes():
    assert reading_to_score({"main": {"aqi": 2}, "components": {"pm2_5": 30.0}}) == 200.0
    assert reading_to_score({"aqi": 2, "components": {"pm2_5": 15}}) == 100.0
    for bad in ({}, {"components": None}, {"components": {"pm10": 1}}, "reading", None):
        with pytest.raises(ValueError):
            reading_to_score(bad)


def test_add_category_and_score_copies_and_is_repeatable():
    readings = [
        {"aqi": 2, "components": {"pm2_5": 3.25}},
        {"main": {"aqi": 4.0}, "components": {"pm2_5": 45}},
    ]
    original = copy.deepcopy(readings)
    once = add_category_and_score(readings)
    assert readings == original
    assert [(r["aqi_category"], r["risk_score"]) for r in once] == [
        ("Fair", pytest.approx(21.666666666666668)), ("Poor", 300.0)]
    assert add_category_and_score(once) == once
    assert add_category_and_score([]) == []


def test_add_category_and_score_names_the_bad_index_and_never_defaults():
    with pytest.raises(ValueError, match=r"readings\[1\].*aqi"):
        add_category_and_score([{"aqi": 1, "components": {"pm2_5": 1}}, {"aqi": 9, "components": {"pm2_5": 1}}])
    with pytest.raises(ValueError, match=r"readings\[0\].*pm2_5"):
        add_category_and_score([{"aqi": 1, "components": {}}])
    with pytest.raises(ValueError):
        add_category_and_score(None)
