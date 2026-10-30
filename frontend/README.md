# Website Intelligence — frontend

React + Vite workspace UI.

## Develop

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173/app/ — Vite proxies `/api` and `/data` to the FastAPI server on `:8000`.

## Production build (served by FastAPI at `/app/`)

```bash
cd frontend
npm install
npm run build
```

FastAPI mounts `frontend/dist` when it exists.
