from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


# GeoJSON uses [longitude, latitude]
Coordinate = list[float]


class GeoJSONPoint(BaseModel):
    """
    GeoJSON Point geometry representing a geographic position.
    Coordinates use [longitude, latitude].
    """

    type: Literal["Point"]
    coordinates: Coordinate

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coordinate: Coordinate) -> Coordinate:
        if len(coordinate) != 2:
            raise ValueError(
                "Each GeoJSON coordinate must be [longitude, latitude]."
            )

        lon, lat = coordinate

        if not -180 <= lon <= 180:
            raise ValueError(
                "Longitude must be between -180 and 180."
            )

        if not -90 <= lat <= 90:
            raise ValueError(
                "Latitude must be between -90 and 90."
            )

        return coordinate


class GeoJSONLineString(BaseModel):
    """
    GeoJSON LineString representing track geometry.
    Coordinates use [longitude, latitude].
    """

    type: Literal["LineString"]
    coordinates: list[Coordinate]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, coordinates: list[Coordinate]) -> list[Coordinate]:
        if len(coordinates) < 2:
            raise ValueError(
                "A LineString must contain at least 2 coordinates."
            )

        for coordinate in coordinates:
            if len(coordinate) != 2:
                raise ValueError(
                    "Each GeoJSON coordinate must be [longitude, latitude]."
                )

            lon, lat = coordinate

            if not -180 <= lon <= 180:
                raise ValueError(
                    "Longitude must be between -180 and 180."
                )

            if not -90 <= lat <= 90:
                raise ValueError(
                    "Latitude must be between -90 and 90."
                )

        return coordinates


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[Coordinate]]

    @field_validator("coordinates")
    @classmethod
    def validate_polygon(cls, rings):
        if not rings:
            raise ValueError("Polygon must contain at least one ring.")

        for ring in rings:
            cls._validate_ring(ring)

        return rings

    @staticmethod
    def _validate_ring(ring):
        if len(ring) < 4:
            raise ValueError(
                "A polygon ring must contain at least 4 coordinates."
            )

        if ring[0] != ring[-1]:
            raise ValueError(
                "A polygon ring must be closed "
                "(first and last coordinates must match)."
            )

        for coordinate in ring:
            if len(coordinate) != 2:
                raise ValueError(
                    "Each coordinate must be [longitude, latitude]."
                )

            lon, lat = coordinate

            if not -180 <= lon <= 180:
                raise ValueError(
                    "Longitude must be between -180 and 180."
                )

            if not -90 <= lat <= 90:
                raise ValueError(
                    "Latitude must be between -90 and 90."
                )


class GeoJSONMultiPolygon(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Coordinate]]]

    @field_validator("coordinates")
    @classmethod
    def validate_multi_polygon(cls, polygons):
        if not polygons:
            raise ValueError(
                "MultiPolygon must contain at least one polygon."
            )

        for polygon in polygons:
            if not polygon:
                raise ValueError(
                    "Each polygon in a MultiPolygon must contain "
                    "at least one ring."
                )

            for ring in polygon:
                GeoJSONPolygon._validate_ring(ring)

        return polygons


GeoJSONGeometry = Annotated[
    GeoJSONPolygon | GeoJSONMultiPolygon,
    Field(discriminator="type"),
]
