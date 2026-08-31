"""Service-level tests for the cached demo replay."""
import pytest
from fastapi import HTTPException

from app.models.replay import Replay
from app.data.ais_sample import SHOWCASE_INCIDENT_ID
from app.services.replay import DEMO_INCIDENT_ID, get_replay


def test_demo_replay_is_valid_contract() -> None:
    replay = get_replay(DEMO_INCIDENT_ID)
    # Replay's own model validators enforce chronology + exact intervals.
    assert isinstance(replay, Replay)
    assert replay.incident_id == DEMO_INCIDENT_ID
    assert len(replay.frames) >= 2


def test_demo_replay_has_vessels_and_slick_states() -> None:
    replay = get_replay(DEMO_INCIDENT_ID)
    assert any(f.vessels for f in replay.frames)
    sources = {f.slick.geometry_source for f in replay.frames if f.slick}
    assert sources == {"reconstructed", "observed"}
    assert replay.frames[-1].slick is not None
    assert replay.frames[-1].slick.geometry_source == "observed"


def test_unknown_incident_raises_404() -> None:
    with pytest.raises(HTTPException) as exc:
        get_replay("incident-does-not-exist")
    assert exc.value.status_code == 404


def test_norway_showcase_replay() -> None:
    replay = get_replay(SHOWCASE_INCIDENT_ID)
    assert replay.incident_id == SHOWCASE_INCIDENT_ID
    assert len(replay.frames) == 37  # 18 h window at 30-min interval
    # only the Norway fleet appears (Mumbai fixes are outside this window)
    mmsis = {v.mmsi for f in replay.frames for v in f.vessels}
    assert mmsis <= {"678901234", "789012345", "890123456"}
    assert replay.frames[-1].slick.geometry_source == "observed"
