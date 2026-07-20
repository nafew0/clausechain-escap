# ClauseChain Backend — Django API & Engine Worker

The authoritative web API behind the ClauseChain review console. It mirrors
engine artifacts into immutable snapshots, enforces role-separated review
decisions, and runs engine actions through an argv-allowlisted worker (no shell).

> The judged artifact is the engine (`../engine`). This backend is the optional
> web console — see the root `README.md` and `README_WEB.md`.

## Local setup

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Python 3.12+
pip install -r requirements.txt
cp .env.example .env       # set DJANGO_SECRET_KEY, JWT_SIGNING_KEY, DB settings
python manage.py migrate
python manage.py createsuperuser        # admin (can launch runs)
python manage.py ensure_demo_viewer     # public read-only demo account
python manage.py engine_refresh         # import the engine snapshot (../engine)
python manage.py runserver 8000
```

- **Database:** PostgreSQL in production (`.env`); SQLite works for a quick look.
- **`engine_refresh`** reads `../engine` outputs/review files and creates an
  immutable snapshot (content-hashed). The UI only ever shows snapshot data.
- **Roles:** Django groups `citation_reviewer`, `mapping_reviewer`,
  `status_reviewer`, `admin`. A user with no groups is read-only by
  construction — every decision endpoint requires a role; run-launch requires
  superuser.

## Production sketch (no Docker required)

```
gunicorn (systemd, 127.0.0.1:8001)  <- nginx TLS reverse proxy
engine worker (systemd)             <- polls DB queue; executes ONLY argv
                                       templates from deploy/engine_allowlist.json
                                       (shell=False, output captured + hashed)
```

Point nginx `/api/` at gunicorn and `/` at the frontend server. After each
deploy: `python manage.py migrate && python manage.py engine_refresh` and
restart the two services.
