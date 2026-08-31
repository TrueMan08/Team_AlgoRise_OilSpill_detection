# OilTrace --- API Endpoints & End-to-End Processing Flow

**Version:** 1.0\
**Purpose:** Define the five core API endpoints and describe the
complete OilTrace investigation workflow from oil-spill detection
through source-region hindcasting, vessel matching, attribution, and
frontend replay.

------------------------------------------------------------------------

## 1. Overview

OilTrace is organized as a sequential investigation pipeline:

``` text
Satellite Observation
        │
        ▼
   POST /detect
        │
        ▼
      Slick
        │
        ▼
  POST /hindcast
        │
        ▼
   SourceRegion
        │
        ├──────────────────────┐
        │                      │
        ▼                      ▼
   GET /vessels          Vessel Tracks
        │                      │
        └──────────┬───────────┘
                   ▼
            POST /attribute
                   │
                   ▼
              Attribution
                   │
                   ▼
             GET /replay/{id}
                   │
                   ▼
                Replay
                   │
                   ▼
          Frontend Investigation
```

The five core endpoints are:

  -----------------------------------------------------------------------
  Method                  Endpoint                Primary Purpose
  ----------------------- ----------------------- -----------------------
  `POST`                  `/detect`               Detect an oil slick
                                                  from a satellite image

  `POST`                  `/hindcast`             Estimate probable
                                                  source regions using
                                                  particle backtracking

  `GET`                   `/vessels`              Retrieve candidate
                                                  vessel tracks for a
                                                  spatial/temporal window

  `POST`                  `/attribute`            Rank vessels as
                                                  potential sources using
                                                  evidence

  `GET`                   `/replay/{id}`          Return timeline data
                                                  for frontend animation
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 2. Core Domain Contracts

The API layer operates around the following domain contracts:

``` text
Slick
SourceRegion
Vessel
Attribution
Replay
```

### Slick

Represents the detected oil slick, including its geometry and derived
properties such as centroid, area, and confidence.

### SourceRegion

Represents one or more candidate regions from which the oil could have
originated. Candidate regions may overlap, and each region has an
associated particle-density-derived probability and its own time window.

### Vessel

Represents a vessel relevant to the investigation, including its
identity, track, and AIS-related information.

### Attribution

Represents the ranked assessment of vessels as possible sources,
together with the evidence supporting each assessment.

### Replay

Represents the temporal visualization data required by the frontend. It
contains ordered `ReplayFrame` objects showing the slick and relevant
vessel positions at each timestamp.

------------------------------------------------------------------------

# 3. Endpoint 1 --- `POST /detect`

## Purpose

`/detect` is the entry point into the OilTrace analytical pipeline.

Its responsibility is to identify oil-slick pixels/regions in the
supplied satellite image and transform the detection into the
application's `Slick` domain contract.

``` text
Satellite Image
      │
      ▼
 POST /detect
      │
      ▼
Segmentation / Detection
      │
      ▼
Oil Mask
      │
      ▼
Polygon Extraction
      │
      ▼
Geospatial Transformation
      │
      ▼
Geometry Processing
      │
      ▼
     Slick
```

------------------------------------------------------------------------

## Input

The current V1 design is image-based:

``` text
Content-Type: multipart/form-data

image: TIFF / GeoTIFF
```

The earlier API outline mentioned `image or scene_id`, but for the
current implementation we are treating the uploaded image as the input.

### Important geospatial requirement

A detected polygon initially exists in image/pixel coordinates.

To turn it into the geographic GeoJSON geometry required by `Slick`, the
system must know how image pixels correspond to geographic coordinates.

Therefore, if the uploaded TIFF is expected to provide georeferencing,
it must contain sufficient geospatial information such as:

-   Coordinate Reference System (CRS)
-   Affine/geotransform information
-   Spatial extent/bounds

If the supplied oil-mask TIFF does not contain this metadata, the
georeferencing information must come from another source.

------------------------------------------------------------------------

## Processing Flow

### Step 1 --- Read the image

The service receives the TIFF and reads its raster data.

For an oil-mask image, pixels may represent:

``` text
0 = background
1 = oil
```

The exact pixel encoding depends on the detection pipeline.

### Step 2 --- Detect/segment oil

If the endpoint receives an original satellite image, the
detection/segmentation model produces an oil mask.

Conceptually:

``` text
Satellite Image
      ↓
ML Segmentation
      ↓
Binary Oil Mask
```

If the input itself is already an oil mask, the ML segmentation step can
be skipped and the mask can be processed directly.

### Step 3 --- Extract polygon(s)

The binary mask is converted from raster regions into vector polygons.

``` text
Oil pixels
    ↓
Connected regions / contours
    ↓
Pixel-space polygons
```

### Step 4 --- Georeference the polygons

Pixel coordinates are transformed into geographic coordinates using the
scene's geospatial metadata.

``` text
Pixel Polygon
     ↓
Raster geotransform + CRS
     ↓
Geographic Polygon
```

### Step 5 --- Validate and calculate geometry properties

Shapely can be used for geometric operations such as:

-   polygon validity
-   centroid calculation
-   bounds
-   geometry operations
-   area calculation after appropriate CRS/projection handling

**Important:** Shapely does not determine the geographic location of a
pixel by itself. The raster's georeferencing information is required for
that transformation.

### Step 6 --- Construct `Slick`

The resulting geometry and derived properties are assembled into the
application's `Slick` contract.

------------------------------------------------------------------------

## Output

The endpoint returns:

``` text
Slick
```

The response represents the detected oil slick rather than a separate,
duplicated `DetectResponse` representation.

Conceptually:

``` text
POST /detect
      │
      ▼
    Slick
    ├── geometry
    ├── centroid
    ├── area
    ├── confidence
    └── other Slick metadata
```

------------------------------------------------------------------------

## Use Cases

`/detect` is used when:

1.  A new satellite scene needs to be analyzed.
2.  An operator submits imagery for investigation.
3.  The system needs to turn an oil mask into a standardized `Slick`.
4.  A downstream hindcast operation needs the detected slick's location
    and geometry.

------------------------------------------------------------------------

# 4. Endpoint 2 --- `POST /hindcast`

## Purpose

`/hindcast` works backwards from the observed oil slick to estimate
where the oil could have originated.

The endpoint uses the slick's location together with a time window and
an ocean-drift model such as OpenDrift.

``` text
             Slick
               │
               │ centroid
               │
               ▼
          POST /hindcast
               │
               ├── time window
               │
               ▼
        Ocean / drift model
               │
               ▼
        Particle backtracking
               │
               ▼
       Particle trajectories
               │
               ▼
        Candidate regions
               │
               ▼
          SourceRegion
```

------------------------------------------------------------------------

## Input

The core input is:

``` text
centroid
time window
```

Conceptually:

``` text
HindcastRequest
├── centroid
├── start_time_utc
└── end_time_utc
```

The exact representation of the centroid should reuse the existing
geographic point/geometry contract.

------------------------------------------------------------------------

## Processing Flow

### Step 1 --- Establish the observed location

The slick centroid provides the starting spatial reference for the
hindcast.

### Step 2 --- Establish the relevant time window

The system determines the period over which the particles should be
traced backwards.

### Step 3 --- Configure the drift simulation

The hindcast engine uses environmental information required by the drift
model.

The API contract should expose only the parameters that the caller
actually needs to control. Internal model configuration should remain an
implementation detail unless the system requires otherwise.

### Step 4 --- Backtrack particles

Particles are released/traced through the drift model in reverse time.

``` text
Observed Slick
      │
      ▼
Particle positions
      │
      ▼
Backward trajectories
      │
      ▼
Potential origin locations
```

### Step 5 --- Generate candidate source regions

Particle trajectories are converted into spatial regions representing
where the oil could have originated.

Multiple candidate regions are allowed to overlap.

### Step 6 --- Calculate particle-density-derived probability

The probability associated with a candidate region is derived from
particle density.

In simplified terms:

``` text
More particles
     ↓
Higher density
     ↓
Higher source probability
```

The probability belongs to the candidate region.

### Step 7 --- Associate a time window with each candidate region

Different possible source locations may correspond to different source
times.

Therefore, the time window is attached to each `SourceCandidateRegion`
rather than being treated as one global value for all candidate regions.

------------------------------------------------------------------------

## Output

The endpoint produces a `SourceRegion` result containing candidate
source regions and their probabilities.

Conceptually:

``` text
SourceRegion
├── candidate_region_1
│   ├── geometry
│   ├── probability
│   └── time_window
│
├── candidate_region_2
│   ├── geometry
│   ├── probability
│   └── time_window
│
└── ...
```

------------------------------------------------------------------------

## Use Cases

`/hindcast` is used when:

1.  A detected slick needs to be traced towards possible origins.
2.  The investigation needs probable source locations.
3.  Multiple overlapping source hypotheses need to be preserved.
4.  Source probability needs to be based on particle density.
5.  The attribution stage needs candidate source regions and their
    associated time windows.

------------------------------------------------------------------------

# 5. Endpoint 3 --- `GET /vessels`

## Purpose

`/vessels` retrieves vessel information relevant to the investigation's
spatial and temporal window.

``` text
Source / Investigation Area
          │
          ├── bounding box
          └── time window
                  │
                  ▼
             GET /vessels
                  │
                  ▼
              AIS Data
                  │
                  ▼
          Candidate Vessel Tracks
```

------------------------------------------------------------------------

## Input

The endpoint is a GET request, so the input is represented through query
parameters.

Conceptually:

``` text
GET /vessels
    ?bbox=...
    &start=...
    &end=...
```

### Required concepts

-   Bounding box
-   Start time
-   End time

The bounding box defines the geographic area of interest.

The time window defines the period for which vessel movement should be
retrieved.

------------------------------------------------------------------------

## Processing Flow

### Step 1 --- Determine spatial bounds

The caller provides a bounding box covering the relevant investigation
area.

### Step 2 --- Determine temporal bounds

The caller provides the relevant time window.

This window should normally correspond to the period relevant to the
source-region investigation.

### Step 3 --- Query vessel/AIS data

The system retrieves vessel tracks that intersect the requested spatial
and temporal window.

### Step 4 --- Identify candidate vessels

The returned tracks become candidate vessel data for the attribution
stage.

------------------------------------------------------------------------

## Output

The endpoint returns candidate vessel tracks.

Conceptually:

``` text
VesselsResponse
└── vessels[]
     ├── vessel identity
     ├── track
     ├── AIS information
     └── relevant metadata
```

The exact response should reuse the existing `Vessel` contract rather
than inventing a second vessel representation.

------------------------------------------------------------------------

## Use Cases

`/vessels` is used when:

1.  The system needs vessels operating near a potential source region.
2.  Vessel tracks need to be retrieved for a historical period.
3.  The attribution engine needs vessel movement data.
4.  The frontend needs to display relevant vessel tracks.

------------------------------------------------------------------------

# 6. Endpoint 4 --- `POST /attribute`

## Purpose

`/attribute` is the stage where the system combines the source-region
hypothesis with vessel movement data and produces a ranked attribution.

This is the most important analytical combination stage.

``` text
             SourceRegion
                  │
                  │
                  ├───────────────┐
                  │               │
                  ▼               ▼
             Time windows     Probabilities
                  │
                  │
                  ▼
              /attribute
                  ▲
                  │
             Vessel tracks
                  │
                  ▼
          Evidence evaluation
                  │
                  ▼
             Attribution
```

------------------------------------------------------------------------

## Input

The core input described by the API architecture is:

``` text
source region
time
vessels
```

Conceptually:

``` text
AttributeRequest
├── source_region
├── time information
└── vessels
```

The exact request structure should reference the already-defined
`SourceRegion` and `Vessel` domain contracts where appropriate.

------------------------------------------------------------------------

## Processing Flow

### Step 1 --- Receive candidate source regions

The attribution stage receives the candidate source regions generated by
hindcasting.

Each region carries its probability and associated time window.

### Step 2 --- Receive vessel tracks

Candidate vessel tracks are supplied from the vessel/AIS stage.

### Step 3 --- Match vessels to source regions

For each candidate vessel, the system evaluates how its track relates
spatially and temporally to the candidate source regions.

This is represented by the previously designed source-region matching
structure.

### Step 4 --- Calculate evidence

Evidence is combined into an overall assessment.

The attribution model can contain an `EvidenceScore` and
`SourceRegionMatch` information to explain why a vessel received its
ranking.

### Step 5 --- Rank suspects

Candidate vessels are ranked according to the resulting attribution
assessment.

------------------------------------------------------------------------

## Output

The endpoint returns:

``` text
Attribution
```

Conceptually:

``` text
Attribution
├── suspect 1
│   ├── vessel
│   ├── score
│   ├── evidence
│   └── source-region matches
│
├── suspect 2
│   ├── vessel
│   ├── score
│   ├── evidence
│   └── source-region matches
│
└── ...
```

The important design principle is that the attribution result should be
**explainable** rather than being only a single opaque score.

------------------------------------------------------------------------

## Use Cases

`/attribute` is used when:

1.  Candidate source regions have already been generated.
2.  Relevant vessel tracks have been collected.
3.  Potential source vessels need to be ranked.
4.  The system needs evidence explaining the ranking.
5.  An investigator needs to understand why one vessel is considered
    more likely than another.

------------------------------------------------------------------------

# 7. Endpoint 5 --- `GET /replay/{id}`

## Purpose

`/replay/{id}` provides the temporal data needed by the frontend to
visualize the investigation.

It allows the user to see:

-   where the oil was detected,
-   how the modeled slick evolves,
-   where vessels were located over time,
-   and how the investigation can be traced backwards toward the source
    region.

``` text
Attribution / Investigation
            │
            ▼
      GET /replay/{id}
            │
            ▼
          Replay
            │
            ▼
       Replay Frames
            │
            ▼
       Frontend Timeline
```

------------------------------------------------------------------------

## Input

The endpoint receives the investigation/incident ID:

``` text
GET /replay/{id}
```

------------------------------------------------------------------------

## Processing Flow

The backend retrieves or constructs the replay associated with the
requested incident.

The replay contains chronologically ordered `ReplayFrame` objects.

Each frame represents a single timestamp.

``` text
Replay
│
├── Frame T1
│    ├── slick state
│    └── vessel positions
│
├── Frame T2
│    ├── slick state
│    └── vessel positions
│
├── Frame T3
│    ├── slick state
│    └── vessel positions
│
└── ...
```

------------------------------------------------------------------------

## Replay Frame Design

A `ReplayFrame` answers:

> **Where is everything at this point in time?**

It contains:

``` text
ReplayFrame
├── timestamp_utc
├── slick
└── vessels[]
```

### Slick state

The replay slick state contains the slick geometry applicable at that
timestamp.

It distinguishes:

``` text
observed
reconstructed
```

### Vessel state

Each vessel state contains:

``` text
mmsi
position
position_source
```

The position source can distinguish:

``` text
observed
interpolated
inferred
```

This is important because historical AIS data may contain gaps and the
replay must not present an estimated position as if it were directly
observed.

------------------------------------------------------------------------

## Output

The endpoint returns:

``` text
Replay
```

The `Replay` contains:

``` text
Replay
├── incident_id
├── start_time_utc
├── end_time_utc
├── frame_interval_seconds
└── frames[]
```

------------------------------------------------------------------------

## Use Cases

`/replay/{id}` is used when:

1.  The frontend needs to animate the investigation.
2.  The user wants to trace the oil backwards in time.
3.  Vessel movement needs to be shown alongside the oil.
4.  Observed and reconstructed states need to be distinguished.
5.  The investigation needs a chronological visual explanation.

------------------------------------------------------------------------

# 8. Complete End-to-End Workflow

The complete OilTrace workflow can be viewed as five stages.

## Stage 1 --- Detect the Slick

``` text
Satellite Image
      │
      ▼
   /detect
      │
      ▼
Oil Mask
      │
      ▼
Polygon Extraction
      │
      ▼
Georeferencing
      │
      ▼
Geometry Processing
      │
      ▼
    Slick
```

The output establishes:

> **Where is the oil?**

------------------------------------------------------------------------

## Stage 2 --- Hindcast the Oil

``` text
Slick
  │
  ├── centroid
  └── time window
          │
          ▼
      /hindcast
          │
          ▼
   Particle Backtracking
          │
          ▼
   Particle Trajectories
          │
          ▼
 Candidate Source Regions
          │
          ▼
     SourceRegion
```

The output establishes:

> **Where could the oil have come from?**

------------------------------------------------------------------------

## Stage 3 --- Retrieve Vessel Tracks

``` text
Source Region
     │
     ├── geographic extent
     └── relevant time
              │
              ▼
         /vessels
              │
              ▼
           AIS data
              │
              ▼
       Candidate vessels
```

The output establishes:

> **Which vessels were in the relevant area at the relevant time?**

------------------------------------------------------------------------

## Stage 4 --- Attribute the Source

``` text
SourceRegion ────────┐
                     │
                     ▼
                  /attribute
                     ▲
                     │
Vessel Tracks ───────┘
                     │
                     ▼
               Evidence Analysis
                     │
                     ▼
                Ranked Suspects
                     │
                     ▼
                 Attribution
```

The output establishes:

> **Which vessel is the most plausible source, and why?**

------------------------------------------------------------------------

## Stage 5 --- Replay the Investigation

``` text
                 Investigation
                      │
                      ▼
                /replay/{id}
                      │
                      ▼
                    Replay
                      │
                      ▼
              Chronological Frames
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
        Slick state         Vessel states
            │                   │
            └─────────┬─────────┘
                      ▼
               Frontend Animation
```

The output establishes:

> **How can the entire investigation be explained visually over time?**

------------------------------------------------------------------------

# 9. Data Flow Between Endpoints

The logical data flow is:

``` text
POST /detect
     │
     │ Slick
     ▼
POST /hindcast
     │
     │ SourceRegion
     ├───────────────────────┐
     │                       │
     │                       ▼
     │                 GET /vessels
     │                       │
     │                       │ Vessel[]
     │                       │
     └───────────┬───────────┘
                 ▼
          POST /attribute
                 │
                 │ Attribution
                 ▼
          GET /replay/{id}
                 │
                 │ Replay
                 ▼
              Frontend
```

The important relationships are:

``` text
Slick
  ↓
SourceRegion
  ↓
Vessel
  ↓
Attribution
  ↓
Replay
```

------------------------------------------------------------------------

# 10. Why the API Is Split This Way

The five endpoints correspond to five distinct responsibilities.

  Responsibility                         Endpoint
  -------------------------------------- ----------------
  Computer vision / slick detection      `/detect`
  Ocean-drift source estimation          `/hindcast`
  AIS retrieval                          `/vessels`
  Evidence-based attribution             `/attribute`
  Visualization / investigation replay   `/replay/{id}`

This separation gives each analytical component a clear boundary.

For example:

-   The detection system does not need to know which vessels caused the
    spill.
-   The hindcast system does not need to perform vessel attribution.
-   The vessel service does not need to understand the computer-vision
    model.
-   The attribution system consumes analytical results instead of
    recreating them.
-   The replay service packages the results into frontend-friendly
    temporal data.

------------------------------------------------------------------------

# 11. Domain Contracts vs API Contracts

The domain models and endpoint request/response objects should remain
conceptually separate.

``` text
                  DOMAIN LAYER
        ┌─────────────────────────────┐
        │ Slick                       │
        │ SourceRegion                │
        │ Vessel                      │
        │ Attribution                 │
        │ Replay                      │
        └──────────────┬──────────────┘
                       │
                       ▼
                    API LAYER
        ┌─────────────────────────────┐
        │ DetectRequest               │
        │ HindcastRequest              │
        │ Vessel query parameters      │
        │ AttributeRequest             │
        │ Replay path parameter        │
        └─────────────────────────────┘
```

An API request describes **what an endpoint needs to perform its
operation**.

A domain contract describes **the analytical object produced or consumed
by the system**.

Where the API response is exactly the domain object, there is no need to
create a redundant wrapper solely for the sake of having a `Response`
class.

------------------------------------------------------------------------

# 12. Important V1 Design Decisions

## Detection

-   `/detect` currently receives an image.
-   The working image format is TIFF/GeoTIFF.
-   The system may process an existing oil mask or run a segmentation
    model to create one.
-   Pixel coordinates must be transformed into geographic coordinates
    before constructing geographic GeoJSON.
-   Shapely is used for geometry processing, validation, and derived
    geometry properties.
-   Shapely itself does not provide raster georeferencing.

## Hindcast

-   Candidate source regions may overlap.
-   Probability is derived from particle density.
-   Each candidate source region carries its own time window.
-   The output is represented by `SourceRegion`.

## Vessels

-   Vessel retrieval is based on spatial and temporal constraints.
-   AIS gaps must be represented rather than silently treating missing
    observations as continuous observations.

## Attribution

-   Attribution should be explainable.
-   Rankings should contain evidence, not only a final score.
-   Source-region matches are an important component of the evidence.

## Replay

-   Replay is based on timestamped frames.
-   A frame contains slick state and vessel positions.
-   Slick geometry can be observed or reconstructed.
-   Vessel positions can be observed, interpolated, or inferred.
-   `ReplayEvent` remains an optional future add-on.

------------------------------------------------------------------------

# 13. Future Extension --- Replay Events

`ReplayEvent` is intentionally not part of the five core endpoints' V1
design.

It can later be used for important timeline annotations such as:

``` text
T1 — Slick detected
T2 — Vessel entered candidate source region
T3 — AIS gap detected
T4 — Vessel departed source region
T5 — Highest-probability source time
```

The distinction is:

``` text
ReplayFrame
    = "Where is everything?"

ReplayEvent
    = "What happened?"
```

This allows the frontend to combine continuous spatial animation with
discrete investigation events without overloading `ReplayFrame`.

------------------------------------------------------------------------

# 14. Final Architecture

The resulting OilTrace API can therefore be summarized as:

``` text
┌─────────────────────────────────────────────────────────────┐
│                         OILTRACE                             │
│                                                             │
│  Satellite Image                                            │
│       │                                                     │
│       ▼                                                     │
│  POST /detect                                               │
│       │                                                     │
│       ▼                                                     │
│     Slick                                                   │
│       │                                                     │
│       ▼                                                     │
│  POST /hindcast                                              │
│       │                                                     │
│       ▼                                                     │
│  SourceRegion                                               │
│       │                                                     │
│       ├───────────────────┐                                 │
│       │                   │                                 │
│       ▼                   ▼                                 │
│  GET /vessels        AIS / Vessel Tracks                    │
│       │                   │                                 │
│       └─────────┬─────────┘                                 │
│                 ▼                                           │
│          POST /attribute                                    │
│                 │                                           │
│                 ▼                                           │
│             Attribution                                     │
│                 │                                           │
│                 ▼                                           │
│          GET /replay/{id}                                   │
│                 │                                           │
│                 ▼                                           │
│              Replay                                         │
│                 │                                           │
│                 ▼                                           │
│          Frontend Timeline                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

The five endpoints collectively transform a raw satellite observation
into an explainable investigation:

``` text
DETECT
"Where is the oil?"

        ↓

HINDCAST
"Where could it have come from?"

        ↓

VESSELS
"Which vessels were there?"

        ↓

ATTRIBUTE
"Which vessel is the most plausible source, and why?"

        ↓

REPLAY
"Can we show the entire investigation over time?"
```

This is the intended high-level API and analytical flow for the OilTrace
V1 system.
