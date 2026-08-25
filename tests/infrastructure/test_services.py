from datetime import UTC, datetime
from pathlib import Path

import pytest

from fantasy_football_2026.consensus.common import ConsensusBuilderSupport
from fantasy_football_2026.errors import ContextError, StorageError
from fantasy_football_2026.infrastructure.storage import ArtifactStore
from fantasy_football_2026.infrastructure.web import CachedWebClient, CachePolicy


def test_artifact_store_round_trips_objects_atomically(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "artifact.json"
    store = ArtifactStore()

    store.write_json(path, {"player": "Jahmyr Gibbs", "rank": 1})

    assert store.load_object(path) == {"player": "Jahmyr Gibbs", "rank": 1}
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_artifact_store_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "players.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(StorageError, match="Expected an object"):
        ArtifactStore().load_object(path)


def test_cached_web_client_reads_offline_cache_without_network(tmp_path: Path) -> None:
    cache = tmp_path / "source.html"
    cache.write_text("<h2>Cached source</h2>", encoding="utf-8")
    client = CachedWebClient(
        CachePolicy(refresh=False, offline=True, timeout=1.0),
        now=lambda: datetime(2026, 8, 25, tzinfo=UTC),
    )

    result = client.fetch_text(
        name="source",
        url="https://example.invalid/source",
        cache_path=cache,
    )

    assert result.payload == "<h2>Cached source</h2>"
    assert result.from_cache is True


def test_cached_web_client_fails_closed_when_offline_cache_is_missing(
    tmp_path: Path,
) -> None:
    client = CachedWebClient(CachePolicy(refresh=False, offline=True, timeout=1.0))

    with pytest.raises(ContextError, match="Offline cache is missing"):
        client.fetch_text(
            name="source",
            url="https://example.invalid/source",
            cache_path=tmp_path / "missing.html",
        )


def test_consensus_support_normalizes_sources_and_player_aliases() -> None:
    sources = ConsensusBuilderSupport._sources(
        {
            "sources": [
                {
                    "id": "example",
                    "family": "Example",
                    "url": "https://example.invalid",
                    "players": ["Kenny Gainwell"],
                }
            ]
        },
        default_mode="headings",
        include_players=True,
        catalog_name="test",
    )

    assert sources[0].mode == "headings"
    assert sources[0].players == ("Kenny Gainwell",)
    assert (
        ConsensusBuilderSupport._resolve_name(
            "Kenny Gainwell", {"kenneth gainwell": "Kenneth Gainwell"}
        )
        == "kenneth gainwell"
    )
