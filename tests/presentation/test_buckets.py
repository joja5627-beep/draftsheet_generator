from fantasy_football_2026.presentation.buckets import (
    BUCKET_COLORS,
    context_bucket,
    depth_chart_bucket,
    injury_bucket,
    rank_bucket,
)


def test_rank_bucket_boundaries() -> None:
    assert rank_bucket(1) == "green"
    assert rank_bucket(10) == "green"
    assert rank_bucket(11) == "yellow"
    assert rank_bucket(22) == "yellow"
    assert rank_bucket(23) == "red"
    assert rank_bucket(32) == "red"
    assert rank_bucket("--") == "red"


def test_depth_chart_bucket_boundaries() -> None:
    assert depth_chart_bucket("DST") == "green"
    assert depth_chart_bucket("LWR1") == "green"
    assert depth_chart_bucket("RB2") == "yellow"
    assert depth_chart_bucket("SWR3") == "red"
    assert depth_chart_bucket("--") == "red"


def test_context_bucket_routes_depth_chart_separately() -> None:
    assert context_bucket("DC", "TE2") == "yellow"
    assert context_bucket("OFF", 2) == "green"
    assert context_bucket("OL", 18) == "yellow"
    assert context_bucket("SOS", 28) == "red"
    assert context_bucket("INJ", "0-1") == "yellow"


def test_injury_bucket_uses_upper_end_of_weeks_range() -> None:
    assert injury_bucket(0) == "green"
    assert injury_bucket("0-1") == "yellow"
    assert injury_bucket("1-2") == "yellow"
    assert injury_bucket("3-4") == "red"
    assert injury_bucket("?") == "red"
    assert injury_bucket("--") == "green"


def test_palette_contains_one_coordinated_color_per_bucket() -> None:
    assert set(BUCKET_COLORS) == {"green", "yellow", "red"}
    assert len(set(BUCKET_COLORS.values())) == 3
    assert all(color.startswith("#") and len(color) == 7 for color in BUCKET_COLORS.values())
