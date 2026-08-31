from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.replay_frame import ReplayFrame
from app.models.validation import UTCDateTime

class Replay(BaseModel):
    """
    Complete temporal and spatial replay of an oil-spill incident.

    A Replay contains a sequence of spatial snapshots (`ReplayFrame`)
    covering the investigation period.
    """

    incident_id: str

    start_time_utc: UTCDateTime

    end_time_utc: UTCDateTime

    frame_interval_seconds: int = Field(
        ...,
        gt=0,
    )

    frames: list[ReplayFrame] = Field(
        ...,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_replay(self):
        if self.start_time_utc >= self.end_time_utc:
            raise ValueError(
                "start_time_utc must be earlier than end_time_utc."
            )

        # Ensure frames are chronologically ordered.
        for previous, current in zip(
            self.frames,
            self.frames[1:],
        ):
            if current.timestamp_utc <= previous.timestamp_utc:
                raise ValueError(
                    "Replay frames must be in strictly chronological order."
                )

        # Ensure the first frame lies within the replay window.
        if not (
            self.start_time_utc
            <= self.frames[0].timestamp_utc
            <= self.end_time_utc
        ):
            raise ValueError(
                "The first replay frame must fall within "
                "the replay time window."
            )

        # Ensure the last frame lies within the replay window.
        if not (
            self.start_time_utc
            <= self.frames[-1].timestamp_utc
            <= self.end_time_utc
        ):
            raise ValueError(
                "The last replay frame must fall within "
                "the replay time window."
            )

        # Ensure frames follow the declared interval.
        expected_interval = self.frame_interval_seconds

        for previous, current in zip(
            self.frames,
            self.frames[1:],
        ):
            actual_interval = (
                current.timestamp_utc - previous.timestamp_utc
            ).total_seconds()

            if actual_interval != expected_interval:
                raise ValueError(
                    "Replay frame timestamps must follow "
                    "frame_interval_seconds."
                )

        return self
