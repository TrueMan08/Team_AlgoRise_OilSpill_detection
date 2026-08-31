"""OilTrace backend on Modal (free tier).

Wraps the FastAPI app (app/main.py) unchanged as a Modal ASGI app.
Heavier than the ML service image: OpenDrift + scipy + NetCDF stacks for
/hindcast and /forward. Bundled forcing data (data/*.nc) ships in the image.

Deploy:  PYTHONUTF8=1 python -m modal deploy modal_app.py
"""
import modal

app = modal.App("oiltrace-backend")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgeos-dev", "libproj-dev", "proj-data", "proj-bin")
    .pip_install(
        "fastapi", "uvicorn", "python-multipart", "httpx",
        "pydantic==2.13.4", "pydantic-settings",
        "numpy", "scipy", "shapely", "pyproj",
        "xarray", "netCDF4",
        "opendrift==1.14.11",
    )
    .add_local_dir("app", remote_path="/root/svc/app")
    .add_local_dir("data", remote_path="/root/svc/data")
)


@app.function(
    image=image,
    cpu=2.0,
    memory=4096,               # OpenDrift particle sims are memory-hungry
    min_containers=0,
    scaledown_window=300,
    timeout=600,               # hindcast/forward runs can take minutes
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def web():
    import os
    import sys
    os.chdir("/root/svc")
    sys.path.insert(0, "/root/svc")
    from app.main import app as fastapi_app
    return fastapi_app
