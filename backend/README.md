> **AI agents & new contributors: read [`CONTEXT_BRAIN.md`](CONTEXT_BRAIN.md)
> first, then [`HANDOFF_LOG.md`](HANDOFF_LOG.md) — and log your changes there
> before every push.**

# OilSpill Backend API

A high-performance, modular Python backend built with **FastAPI**, **Pydantic v2**, and **Uvicorn**.

---

## 🚀 Features

- **FastAPI Framework**: Modern, asynchronous, and high-performance Python web API framework.
- **Modular Directory Architecture**: Clean separation of concerns across config, routing, schemas, models, and services.
- **Pydantic v2 Validation**: Strongly-typed request/response validation using `pydantic` and `pydantic-settings`.
- **Environment Management**: Centralized settings loaded from `.env` with validation and defaults.
- **CORS Configured**: Pre-configured cross-origin resource sharing for web/mobile frontend clients.
- **Automated Interactive Docs**: Swagger UI (`/docs`) and ReDoc (`/redoc`) generated out of the box.
- **Testing Suite**: Pytest test suite with FastAPI `TestClient` pre-configured.

---

## 📁 Project Structure

```
OilSpill Backend/
├── .env.example          # Environment variable template
├── .gitignore
├── requirements.txt      # Pinned dependencies (including drift)
├── CONTEXT_BRAIN.md      # AI agent context (read first)
├── HANDOFF_LOG.md        # Change journal (log before every push)
├── Complete_Flow.md      # End-to-end pipeline narrative
├── README.md
├── app/
│   ├── main.py           # Application factory, CORS, lifespan
│   ├── core/
│   │   └── config.py     # Settings (env, drift params, ML service)
│   ├── api/v1/
│   │   ├── api.py        # Router aggregator
│   │   └── endpoints/
│   │       ├── health.py
│   │       ├── detection.py
│   │       ├── hindcast.py     # POST /hindcast, POST /forward
│   │       ├── vessels.py      # (stub — Nimit)
│   │       ├── attribution.py  # (stub — Nimit)
│   │       └── replay.py       # (stub — Sayan)
│   ├── models/           # Domain contracts (Pydantic v2, strict)
│   ├── schemas/
│   │   ├── health.py
│   │   └── hindcast.py   # HindcastRequest/Response, Forward*
│   └── services/
│       ├── detection.py  # ML service proxy (Satyam)
│       ├── hindcast.py   # Backward hindcast + forward counterfactual
│       ├── vessels.py    # (stub — Nimit)
│       ├── attribution.py # (stub — Nimit)
│       └── replay.py     # (stub — Sayan)
├── tests/
│   ├── conftest.py
│   ├── test_hindcast_service.py  # 31 drift tests
│   └── ...                       # contract + endpoint tests
└── docs/                 # API reference, per-object docs
```

---

## 🛠️ Quick Start

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)

### 2. Set Up Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `opendrift` has heavy transitive dependencies (cartopy, netCDF4,
> geopandas).  On first install, this may take several minutes.

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` to customize settings.  Key drift-specific variables:

| Variable | Description | Default |
|---|---|---|
| `DRIFT_FORCING_CURRENTS_PATH` | Path to ocean current NetCDF file | `data/currents.nc` |
| `DRIFT_FORCING_WIND_PATH` | Path to wind NetCDF file | `data/wind.nc` |
| `DRIFT_PARTICLE_COUNT` | Number of Lagrangian particles | `1000` |
| `DRIFT_OIL_TYPE` | ADIOS oil type string | `GENERIC BUNKER C` |
| `DRIFT_DEFAULT_DURATION_HOURS` | Default backward simulation hours | `12` |

### 5. Provide Forcing Data

The drift simulation requires **ocean current** and **wind** NetCDF files.
These are external runtime assets — they are NOT committed to the repository.

Place them at the paths configured in `.env`, or set absolute paths.
The files must be readable by OpenDrift's `reader_netCDF_CF_generic`.

---

## 🏃 Running the Application

```bash
# Development server with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or via module
python -m app.main
```

The API will be accessible at: `http://localhost:8000`

---

## 📖 API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Running Tests

```bash
python -m pytest tests -q
```

All 131 tests must pass before any push.

---

## 🌐 Endpoints Overview

| Method | Endpoint | Description | Owner |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | API root | Parth |
| `GET` | `/api/v1/health` | Health status | Parth |
| `GET` | `/api/v1/ping` | Uptime probe | Parth |
| `GET` | `/api/v1/health/ml` | ML service health | Satyam |
| `POST` | `/api/v1/detect` | SAR oil-spill detection | Satyam |
| `POST` | `/api/v1/hindcast` | Backward drift → source region | Ved |
| `POST` | `/api/v1/forward` | Forward counterfactual simulation | Ved |
| `GET` | `/api/v1/vessels` | AIS query/filter (stub) | Nimit |
| `POST` | `/api/v1/attribute` | Attribution scoring (stub) | Nimit |
| `GET` | `/api/v1/replay/{id}` | Timeline replay (stub) | Sayan |
