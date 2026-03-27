# Backend

Run the API locally:

```powershell
cd backend
.\run_backend.ps1
```

Default URL: `http://127.0.0.1:8000`

Notes:
- The backend now defaults to a local SQLite database at the repo root: `medicycle.db`
- Set `DATABASE_URL` if you want PostgreSQL instead

## Render

For Render deployment with Supabase/Postgres:
- Use `DATABASE_URL=postgresql+psycopg://...`
- Set `SECRET_KEY`
- Optionally set `GEMINI_API_KEY`

The repo root includes `render.yaml` for a Render Blueprint deployment.
