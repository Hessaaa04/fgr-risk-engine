from riskcore.calendar import month_end, month_open, ym_add, ym_range


def test_ym_add_crosses_years():
    assert ym_add("2025-12", 1) == "2026-01"
    assert ym_add("2026-01", -1) == "2025-12"
    assert ym_add("2026-03", -27) == "2023-12"


def test_ym_range_inclusive():
    assert ym_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_month_open_until_last_day():
    assert month_end("2024-02") == "2024-02-29"
    assert month_open("2026-11", "2026-11-30") is True
    assert month_open("2026-11", "2026-12-01") is False
