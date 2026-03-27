# Frontend

Run the static frontend locally:

```powershell
cd frontend
.\run_frontend.ps1
```

Default URL: `http://127.0.0.1:3000`

Notes:
- The frontend reads the backend base URL from `config.js`
- By default it points to `http://127.0.0.1:8000`
- You can override it with `?api_url=http://your-api-host:8000`
