from tori_fuel import voyage_types as vt


def test_base_voyage_strips_suffixes():
    assert vt.base_voyage("LGD-2602-1") == "LGD-2602"
    assert vt.base_voyage("LGD-2603B") == "LGD-2603"
    assert vt.base_voyage("LGD-T65-B") == "LGD-T65"
    assert vt.base_voyage("LGD-2417S-3") == "LGD-2417"
    assert vt.base_voyage("LGD-2601") == "LGD-2601"
    assert vt.base_voyage("") == ""


def test_classify_voyage_by_client():
    assert vt.classify_voyage("國科會", "任昊佳") == vt.TYPE_NSTC
    assert vt.classify_voyage("中研院", "戴仁華") == vt.TYPE_SINICA
    assert vt.classify_voyage("內政部＋國海院", "—") == vt.TYPE_HYDRO
    assert vt.classify_voyage("試航", "—") == vt.TYPE_TRIAL
    assert vt.classify_voyage("地礦中心", "") == vt.TYPE_GEO
    assert vt.classify_voyage("中華電信", "") == vt.TYPE_CHT


def test_seismic_keyword_overrides_client():
    assert vt.classify_voyage("國科會", "許樹坤(震測)") == vt.TYPE_SEISMIC
    assert vt.classify_voyage("TORI", "鄧家明(震測)") == vt.TYPE_SEISMIC


def test_dock_classification():
    assert vt.classify_voyage("—", "進塢維修") == vt.TYPE_DOCK


def test_history_voyage_type_fallbacks():
    mapping = {"LGD-2601": vt.TYPE_NSTC}
    assert vt.type_of_history_voyage("LGD-2601", mapping) == vt.TYPE_NSTC
    assert vt.type_of_history_voyage("LGD-T59", mapping) == vt.TYPE_TRIAL
    assert vt.type_of_history_voyage("LGD-2412", mapping) == vt.TYPE_OTHER
