from fantasy_football_2026.sources.teams import (
    TEAM_NAMES,
    parse_first_down_totals,
    parse_sharp_offensive_lines,
)


def test_parses_first_down_team_rows() -> None:
    body = "".join(
        f"<tr><td>{rank}</td><td>{names[1]}</td><td>{27 - rank / 4:.1f}</td></tr>"
        for rank, names in enumerate(TEAM_NAMES.values(), start=1)
    )
    rows = f"<table>{body}</table>"

    parsed = parse_first_down_totals(rows)

    assert len(parsed) == 32
    assert parsed["ARI"] == (1, 26.8)


def test_parses_sharp_markdown_rows() -> None:
    rows = "\n".join(
        f"| {rank} | {names[0]} | {101 - rank} |"
        for rank, names in enumerate(TEAM_NAMES.values(), start=1)
    )

    parsed = parse_sharp_offensive_lines(rows)

    assert len(parsed) == 32
    assert parsed["ARI"] == (1, 100)
