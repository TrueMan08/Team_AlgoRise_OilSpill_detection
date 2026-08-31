from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.attribution import Attribution
from app.models.replay import Replay
from app.models.satellite_scene import SatelliteScene
from app.models.slick import Slick
from app.models.source_region import SourceRegion
from app.models.vessel import Vessel
from app.models.validation import UTCDateTime


class Incident(BaseModel):
    """
    Root aggregate for an oil-spill investigation.

    An Incident ties together the detected slick, satellite scene,
    candidate vessels, attribution scores, and temporal replay into
    a single investigative unit.
    """

    id: str

    # Current lifecycle status of the investigation.
    status: Literal[
        "detected",
        "analyzing",
        "attributed",
        "resolved",
        "false_positive",
    ]

    # When the incident was first detected by the system.
    detected_at_utc: UTCDateTime

    # When the incident record was last modified.
    updated_at_utc: UTCDateTime

    # --------------- Core Evidence ---------------

    # The satellite scene that produced this detection.
    scene: SatelliteScene

    # The detected oil slick.
    slick: Slick

    # Back-projected source region analysis.
    source_region: SourceRegion | None = None

    # --------------- Vessel Correlation ---------------

    # All vessels identified in the spatial-temporal vicinity.
    candidate_vessels: list[Vessel] = Field(
        default_factory=list,
    )

    # Ranked attribution scores for candidate vessels.
    attributions: list[Attribution] = Field(
        default_factory=list,
    )

    # --------------- Replay / Visualisation ---------------

    # Temporal replay of the incident for dashboard playback.
    replay: Replay | None = None

    # --------------- Validators ---------------

    @model_validator(mode="after")
    def validate_timestamps(self):
        if self.updated_at_utc < self.detected_at_utc:
            raise ValueError(
                "updated_at_utc must be greater than or equal "
                "to detected_at_utc."
            )
        return self

    @model_validator(mode="after")
    def validate_attributions(self):
        if self.slick.scene_id is not None and self.slick.scene_id != self.scene.scene_id:
            raise ValueError("slick.scene_id must match scene.scene_id.")

        if self.source_region is not None and self.source_region.slick_id != self.slick.id:
            raise ValueError("source_region.slick_id must match slick.id.")

        if self.replay is not None and self.replay.incident_id != self.id:
            raise ValueError("replay.incident_id must match incident.id.")

        candidate_mmsis = [vessel.mmsi for vessel in self.candidate_vessels]
        if len(candidate_mmsis) != len(set(candidate_mmsis)):
            raise ValueError("Candidate vessel MMSIs must be unique within an incident.")

        # Replay states are snapshots of the incident's candidate vessels.
        if self.replay is not None:
            candidate_mmsi_set = set(candidate_mmsis)
            for frame in self.replay.frames:
                unknown_mmsis = {
                    vessel.mmsi for vessel in frame.vessels
                } - candidate_mmsi_set
                if unknown_mmsis:
                    raise ValueError(
                        "Replay contains a vessel that is not an incident candidate."
                    )

        if not self.attributions:
            return self

        # All attributions must reference this incident.
        for attribution in self.attributions:
            if attribution.incident_id != self.id:
                raise ValueError(
                    "All attributions must reference this incident's ID."
                )

        # Attribution ranks must be unique.
        ranks = [a.rank for a in self.attributions]
        if len(ranks) != len(set(ranks)):
            raise ValueError(
                "Attribution ranks must be unique within an incident."
            )

        # Each attributed MMSI must correspond to a candidate vessel.
        candidate_mmsis = {v.mmsi for v in self.candidate_vessels}
        for attribution in self.attributions:
            if attribution.mmsi not in candidate_mmsis:
                raise ValueError(
                    f"Attribution MMSI {attribution.mmsi} does not "
                    f"match any candidate vessel."
                )

        attributed_mmsis = [attribution.mmsi for attribution in self.attributions]
        if len(attributed_mmsis) != len(set(attributed_mmsis)):
            raise ValueError("Each vessel may have only one attribution per incident.")

        if self.source_region is None:
            if any(attribution.matched_source_regions for attribution in self.attributions):
                raise ValueError(
                    "Matched source regions require an incident source_region."
                )
        else:
            source_ids = {region.id for region in self.source_region.candidate_regions}
            for attribution in self.attributions:
                if any(
                    match.source_candidate_region_id not in source_ids
                    for match in attribution.matched_source_regions
                ):
                    raise ValueError(
                        "Attribution references an unknown source candidate region."
                    )

        return self
