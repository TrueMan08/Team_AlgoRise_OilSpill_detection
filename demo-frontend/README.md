# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.


### Stability patch
The map camera and oil particle layer are isolated from vessel-selection UI state. Selecting a vessel must not animate, refit, resize, recreate, or transform the oil field.

## Backend integration (OilTrace)

Local development talks to a backend on your machine. Production talks to Modal.

| Mode | Command | API |
|---|---|---|
| Development | `npm run dev` | `http://localhost:8000/api/v1` (Vite proxies `/api` → localhost:8000) |
| Production build | `npm run build` | `https://vscimatic999--oiltrace-backend-web.modal.run/api/v1` |

Start the FastAPI app from the **backend** repo (not this frontend repo):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Config lives in `.env.development` / `.env.production` (`VITE_API_BASE_URL`).
Axios does **not** fail over to Modal during `npm run dev`, so local work does not
consume Modal credits. Override with `.env.local` if needed (see `.env.example`).

"Run hindcast" executes hindcast → AIS → attribution → forward → counterfactual
against whichever host the env points at. The map shows coordinates returned by
that API.

The ML detection demo on Modal is **off** in local development (`VITE_USE_MODAL_ML=false`).
Set it to `true` only if you explicitly want the Modal ML scene.

The canonical SIH demo is Eastern Mediterranean / Cyprus (`incident-mediterranean-001`).
Source region, AIS ranking, forward drift, and replay come from the backend API.
