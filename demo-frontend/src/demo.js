// Norway demo scenario — DEMO INPUT ONLY.
// Everything downstream (source region, rankings, scores, trajectories,
// footprints, counterfactual results) comes from the backend, never from here.

export const DEMO_INCIDENT_ID = "norway-test-001";

// Observed slick for the deterministic Norway scenario (spec §20).
// Sits inside the bundled forcing-data window (lon 4–6, lat 59–61, 20–22 Aug 2025)
// and overlaps the synthetic Norway AIS vessels' activity window.
// Slick placement is designed to be physically self-consistent with the
// bundled forcing data: a forward OpenDrift run from the demo tanker's track
// (release ~10:15 UTC) lands its footprint centred near (4.487 E, 60.106 N)
// at 12:00 UTC — so the observed slick lives there.
export const DEMO_SLICK = {
  id: "slick-norway-test-001",
  timestamp_utc: "2025-08-20T12:00:00Z",
  centroid: { lat: 60.106, lon: 4.487 },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [4.455, 60.093],
        [4.487, 60.086],
        [4.520, 60.095],
        [4.531, 60.108],
        [4.512, 60.121],
        [4.478, 60.126],
        [4.452, 60.113],
        [4.455, 60.093],
      ],
    ],
  },
  area_km2: 14.8,
  confidence: 0.77,
  sensor: "Sentinel-1",
  scene_id: "DEMO-NORWAY-S1-001",
};

// Real Sentinel-1 SAR imagery (Zenodo dataset, CC-BY 4.0) used as the
// detection-stage visual. Labeled as demo scenario imagery in the UI.
export const SAR_VIEWS = [
  { id: "overlay", label: "Detection overlay", src: "/sar/scene_overlay.png",
    caption: "Detected slick mask (orange) over Sentinel-1 VH backscatter" },
  { id: "vh", label: "VH channel", src: "/sar/scene_vh.png",
    caption: "Sentinel-1 VH σ° — slick appears as dark damped region" },
  { id: "vv", label: "VV channel", src: "/sar/scene_vv.png",
    caption: "Sentinel-1 VV σ° — same scene; slick barely visible" },
];

export const SAR_CREDIT =
  "SAR imagery: Trujillo-Acatitla et al., Zenodo (CC-BY 4.0) · Demo scenario";
