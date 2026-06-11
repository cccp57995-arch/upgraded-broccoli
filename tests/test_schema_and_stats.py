import pandas as pd
import pytest

from tori_fuel import classifier, schema, stats
from tori_fuel.sample_data import make_sample_daily_log, make_sample_voyages


def test_guess_mapping_chinese_headers():
    raw = make_sample_daily_log(days=5)
    mapping = schema.guess_mapping(list(raw.columns), schema.DAILY_LOG_FIELDS)
    assert mapping["date"] == "日期"
    assert mapping["total_fuel_consumed"] == "總油耗(KL)"
    assert mapping["rob"] == "ROB(KL)"
    assert mapping["refuel"] == "加油量(KL)"
    assert mapping["propulsion_fuel"] == "推進油耗(KL)"


def test_apply_mapping_requires_mandatory_fields():
    df = pd.DataFrame({"x": [1]})
    with pytest.raises(ValueError):
        schema.apply_mapping(df, {"date": None}, schema.DAILY_LOG_FIELDS)


def test_apply_mapping_standardizes_columns():
    raw = make_sample_daily_log(days=10)
    mapping = schema.guess_mapping(list(raw.columns), schema.DAILY_LOG_FIELDS)
    std = schema.apply_mapping(raw, mapping, schema.DAILY_LOG_FIELDS)
    assert list(std.columns) == list(schema.DAILY_LOG_FIELDS)


def test_voyage_summary_aggregates():
    raw = make_sample_daily_log(days=40)
    mapping = schema.guess_mapping(list(raw.columns), schema.DAILY_LOG_FIELDS)
    std = schema.apply_mapping(raw, mapping, schema.DAILY_LOG_FIELDS)
    classified = classifier.classify_dataframe(std)
    voy_raw = make_sample_voyages()
    voy_map = schema.guess_mapping(list(voy_raw.columns), schema.VOYAGE_FIELDS)
    voyages = schema.apply_mapping(voy_raw, voy_map, schema.VOYAGE_FIELDS)

    summary = stats.voyage_summary(classified, voyages)
    assert not summary.empty
    v = summary.iloc[0]
    sub = classified[classified["voyage_no"] == v["voyage_no"]]
    assert v["total_fuel"] == pytest.approx(sub["total_fuel_consumed"].sum())
    assert v["days"] == sub["date"].nunique()
    assert v["client"] == "國海院"
