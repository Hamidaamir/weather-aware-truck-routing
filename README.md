# Weather-Aware Truck Routing

A production-style MVP for dispatchers to compare up to three route alternatives using weather risk, ETA, and route-stability scoring.

## Product overview

This application accepts an origin, destination, departure time, load weight, checkpoint interval, and forecast offset, then queries the backend for route alternatives and weather conditions along each route. The backend ranks candidates using the specification-driven algorithm and surfaces risk thresholds, coverage warnings, and route recommendations.

## Architecture

- Backend: Django + Django REST Framework
- Frontend: React + TypeScript + Vite + Tailwind + React Leaflet
- APIs: OpenRouteService for route generation and geocoding, Open-Meteo for weather forecasts
- Risk engine: dedicated Python classification and ranking logic
- Location entry: labeled popular US starting suggestions and debounced OpenRouteService search served through Django so the API key remains server-side

## Directory structure

```text
weather-aware-truck-routing/
├── README.md
├── .gitignore
├── .python-version
├── backend/
│   ├── .env.example
│   ├── manage.py
│   ├── requirements.txt
│   ├── api/
│   ├── config/
│   ├── routing/
│   ├── services/
│   └── tests/
└── frontend/
    ├── .env.example
    ├── package.json
    ├── vite.config.ts
    └── src/
```

## Environment configuration

### Backend
Copy `backend/.env.example` to `backend/.env` and populate values.

```powershell
if (-not (Test-Path .\backend\.env)) { Copy-Item .\backend\.env.example .\backend\.env }
```

Required values:

- `DJANGO_SECRET_KEY`: Django secret key
- `DEBUG`: `True` or `False`
- `ALLOWED_HOSTS`: comma-separated values such as `127.0.0.1,localhost`
- `ORS_API_KEY`: OpenRouteService API key
- `ORS_TIMEOUT_SECONDS`: provider read-timeout ceiling default `15` seconds
- `OPEN_METEO_TIMEOUT_SECONDS`: provider read-timeout ceiling default `15` seconds
- `CORS_ALLOWED_ORIGINS`: comma-separated frontend origins; defaults to `http://localhost:5173,http://127.0.0.1:5173`

### Frontend
Copy `frontend/.env.example` to `frontend/.env`.

```powershell
if (-not (Test-Path .\frontend\.env)) { Copy-Item .\frontend\.env.example .\frontend\.env }
```

Required value:

- `VITE_API_BASE_URL=http://localhost:8000/api`

## Deployment: PythonAnywhere and Vercel

The deployed frontend is hosted on Vercel at `https://weather-aware-truck-routing-orcin.vercel.app/`, and the Django API is hosted on PythonAnywhere at `https://hamidaamir.pythonanywhere.com/`. The frontend calls `https://hamidaamir.pythonanywhere.com/api` through `VITE_API_BASE_URL`. The backend is a stateless JSON API; route and weather results are computed per request. SQLite is used only for Django's default auth/admin tables and is not required for route planning.

### PythonAnywhere backend configuration

The PythonAnywhere web app uses:

- Project/backend directory: `/home/hamidaamir/weather-aware-truck-routing/backend`
- Virtual environment: `/home/hamidaamir/.virtualenvs/weather-routing-venv`
- Django settings module: `config.settings`
- Allowed host: `hamidaamir.pythonanywhere.com`
- `DEBUG=False`

The settings use `python-dotenv` to load `backend/.env` when present, then read configuration from the process environment. A process environment variable takes precedence over the `.env` value. The local `.env` is ignored by Git and is not uploaded with the repository.

To configure the OpenRouteService key on PythonAnywhere, create a private `.env` file in the backend directory using the PythonAnywhere Files page or a server-side editor. Put the key in the file as `ORS_API_KEY=...`; do not put it in tracked code, the WSGI file, or a frontend environment variable. Restrict its permissions from a PythonAnywhere Bash console:

```bash
chmod 600 /home/hamidaamir/weather-aware-truck-routing/backend/.env
```

Set these production values in the same private backend `.env` file, or supply them through the server process environment if you already manage that securely:

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY` | A private, strong Django secret |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `hamidaamir.pythonanywhere.com` |
| `CORS_ALLOWED_ORIGINS` | `https://weather-aware-truck-routing-orcin.vercel.app` |
| `ORS_API_KEY` | Your private OpenRouteService key |
| `ORS_TIMEOUT_SECONDS` | `15` (optional; this is the default) |
| `OPEN_METEO_TIMEOUT_SECONDS` | `15` (optional; this is the default) |

Use the existing PythonAnywhere WSGI configuration to point at the backend directory, activate the specified virtual environment, and set `DJANGO_SETTINGS_MODULE` to `config.settings`; do not add secrets to the WSGI file. After changing code, environment values, or `.env`, click **Reload** for the web app in PythonAnywhere's **Web** tab. Verify `https://hamidaamir.pythonanywhere.com/api/health/`, then test geocoding and route planning. The API returns a clear HTTP 503 configuration error if `ORS_API_KEY` is genuinely missing.

The backend uses Django 5.2.18 LTS and Django REST Framework 3.18.3. Static files are configured with WhiteNoise and `collectstatic`; the frontend itself is not served by Django. The repository's `.python-version` is for services such as Render; PythonAnywhere uses the interpreter selected for its virtual environment.

### Vercel frontend configuration

Configure the Vercel project with root directory `frontend`, Vite framework preset, install command `npm ci`, build command `npm run build`, and output directory `dist`. Set this environment variable for the production deployment:

```text
VITE_API_BASE_URL=https://hamidaamir.pythonanywhere.com/api
```

Redeploy the frontend after changing its environment variables or source. The Vite client uses the localhost API fallback only in development; a production build without `VITE_API_BASE_URL` fails clearly rather than sending requests to localhost. The application does not use client-side routes, so a Vercel SPA rewrite is not needed.

## Windows PowerShell setup

### Backend

Run from the repository root:

```powershell
if (-not (Test-Path .\.venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt
if (-not (Test-Path .\backend\.env)) { Copy-Item .\backend\.env.example .\backend\.env }
Set-Location .\backend
python manage.py check
python manage.py test
python manage.py runserver
```

If execution policy blocks activation, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Frontend

```powershell
cd .\frontend
npm install
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
npm run test
npm run build
npm run dev
```

## Local startup

Backend:

```powershell
cd "C:\path\to\Weather-Aware Truck Routing"
.\.venv\Scripts\Activate.ps1
Set-Location .\backend
python manage.py runserver
```

Frontend:

```powershell
cd .\frontend
npm run dev
```

Open the frontend at `http://localhost:5173`.

## API behavior

### Health endpoint

```http
GET /api/health/
```

Returns a simple status payload for Django service health checks.

### Location suggestions

```http
GET /api/geocode/?q=Dallas
```

The query must contain 3–120 characters. Results are restricted to the United States using the OpenRouteService `boundary.country=USA` geocoding filter; results with explicit non-US country metadata are also excluded. The response includes a provider identifier, primary/secondary display text, a human-readable label, and coordinates.

Focusing an empty field or clearing it shows a compact, explicitly labeled list of popular US cities. These curated starting points are not a complete US location database and do not require a provider request. Typing at least three characters switches to live OpenRouteService suggestions. Searches are debounced by 300 ms, and stale requests are cancelled or disregarded. A location must be selected before the existing route-plan request can be submitted. Its contract continues to accept textual `origin` and `destination` values; coordinates are retained in the UI for duplicate-place checks but are not added to that contract.

OpenRouteService geocoding failures are reported with suitable status codes (including 429 for rate limits and 504 for timeouts). No API key is exposed to the browser. Location autocomplete uses the existing OpenRouteService configuration and does not add a paid provider dependency.

### Route plan endpoint

```http
POST /api/route-plan/
```

Example payload:

```json
{
  "origin": "Dallas, TX",
  "destination": "El Paso, TX",
  "departure_datetime": "2026-10-28T08:00:00-05:00",
  "load_weight_lbs": 35000,
  "checkpoint_interval_miles": 25,
  "forecast_offset_hours": 0
}
```

The backend validates the request and returns route alternatives, checkpoints, weather risk calculations, coverage details, and recommendation metadata. Directions are requested from `POST https://api.openrouteservice.org/v2/directions/driving-car/geojson` with server-side authorization and GeoJSON output. The provider response is parsed as a GeoJSON FeatureCollection. If the alternatives request is rejected or returns malformed alternative geometry, the backend retries standard directions and returns only the real route received from the provider, with a warning that alternatives were unavailable.

The routing integration had several confirmed failures. An earlier request to the `/geojson` endpoint used an incompatible `Accept: application/json` header (upstream HTTP 406); the alternative-route parameters used an unsupported request field; and the response parser did not read GeoJSON FeatureCollection features. After correcting those issues, a live Dallas–El Paso request confirmed that ORS restricts alternative-route searches to an approximated route distance of 100 km (upstream error 2004). Its standard-route retry then failed because the geocoded El Paso city point was not within the default 350 m of a routable road (upstream error 2010). The request now omits the conflicting header, uses the documented top-level `alternative_routes` fields, parses GeoJSON features, and retries a standard route with a 2 km waypoint snap radius after a default-radius 404. Alternative availability may still depend on provider constraints; the standard-route fallback returns only a real provider route and never fabricates alternatives.

## Route-generation performance

The route-plan API records structured stage timings for geocoding, routing, geometry/checkpoint generation, weather processing, risk/ranking, response serialization, and total request time. Provider logs record each ORS/Open-Meteo request duration, status, attempt, and weather location count without logging coordinates or credentials. The frontend console reports route-plan fetch plus response-parsing time. Progress is presented as one honest in-flight state because the synchronous route-plan API does not stream internal stages.

Open-Meteo accepts comma-separated latitude/longitude coordinates and returns one forecast object per location. Checkpoints for all route alternatives are gathered before weather evaluation, exact duplicate coordinates are coalesced, and forecasts are fetched in batches of up to 50 locations. Larger plans use at most three concurrent batch requests; result-to-coordinate mapping is retained even when batches finish out of order. Only wind, rain, snow, and UTC hourly times are requested.

Provider sessions use connection pooling with no automatic retries, a 3-second connection timeout, and a read timeout capped at 15 seconds. OpenRouteService alternatives are skipped when the straight-line distance already exceeds the provider's observed 100 km alternative-route limit; this lower bound cannot exceed the routed distance. Shorter routes still request alternatives normally.

Django's process-local memory cache stores geocoding results for one hour, route geometry for 15 minutes, and weather forecasts for five minutes. These TTLs avoid repeated upstream work without a Redis dependency; each app process has its own cache, so cache hits are not shared across multiple workers or machines. Weather coverage/checkpoints are never omitted to save time. Checkpoint interpolation now reuses cumulative route distances and binary-searches the containing segment while keeping original geometry intact.

Repeatable mocked processing benchmark (no provider/network latency):

```powershell
cd .\backend
python benchmark_route_plan.py --runs 5
```

Recorded live Dallas–El Paso observations before and after the optimization, using the same backend route-plan function inputs:

| Measurement | Before | After |
|---|---:|---:|
| Direct backend route-plan function elapsed | 46,796.7 ms | 4,749.4 ms |
| Geocoding | 2 sequential calls (4,653 ms combined) | 2 parallel lookups (1,740 ms stage) |
| Geometry/checkpoint generation | Not separately timed | 8.5 ms for 27 checkpoints |
| Weather processing | 27 sequential calls (about 34.2 s combined) | 1 batch for 27 checkpoints (1,386 ms stage; one request took 1,380 ms) |
| ORS directions | 3 sequential attempts (about 7.4 s combined) | 2 standard attempts (1,614 ms combined) |
| Risk and ranking | Not separately timed | 0.2 ms |
| Total external provider requests | 32 | 5 |

The original run spent most of its time waiting on one weather HTTP request per checkpoint. The optimized direct function run was about 89.9% faster in these individual observations; provider/network timing varies and this is not a service-level guarantee. A separate browser run after the change completed the frontend request/response path in 6,815 ms, including browser/network and JSON handling; there is no equivalent measured pre-change browser run to compare it against.

A separate live endpoint measurement returned HTTP 200 in 4,778.7 ms wall time. The instrumented view recorded 4,702.3 ms total before response return and 21.3 ms to construct/serialize JSON. Its stage/provider timings were also logged; they vary between requests.

The mocked benchmark was also run before optimization on the same synthetic 10,000-point route: one baseline run took 724.2 ms with 15 sequential mocked 20 ms weather waits; the optimized benchmark's five-run median was 39.9 ms with one mocked 20 ms batch wait and the same 15 checkpoints. The baseline was a single observation, whereas the optimized figure is the median of five runs. This compares local processing and a controlled delay only; it is not a live-provider benchmark.

For ongoing live timings, submit a route through the application and compare the `route_plan_stage`, `provider_request`, `weather_batch_complete`, `route_plan_request`, and `route_plan_frontend_timing` log/console records. Live API timings vary with provider, network, cache state, and current service load; benchmark output is not a prediction of provider latency.

## Risk thresholds

Wind speed thresholds are expressed in mph:

- Low: < 25
- Moderate: 25 to < 35
- High: 35 to < 45
- Severe: 45 to < 55
- No Travel: >= 55

Rain rate thresholds are expressed in inches per hour:

- Low: < 0.10
- Moderate: 0.10 to < 0.25
- High: 0.25 to < 0.50
- Severe: 0.50 to 1.00
- No Travel: > 1.00

Snow rate thresholds are expressed in inches per hour:

- Low: < 0.5
- Moderate: 0.5 to < 1.0
- High: 1.0 to < 2.0
- Severe: 2.0 to 3.0
- No Travel: > 3.0

Load-related wind rules:

- Wind >= 55 mph: No Travel for all loads
- Wind 45 to < 55 mph: No Travel when load > 30,000 lb
- Wind 35 to < 45 mph: Severe when load > 40,000 lb

The checkpoint risk uses the highest applicable individual risk. No Travel always takes precedence.

## Recommendation ranking

Routes are ranked lexicographically in this priority order:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest estimated travel time

Safety policy:

- A route with confirmed No Travel exposure is ineligible when another route has no confirmed No Travel exposure.
- If all routes have confirmed No Travel exposure, none are recommended as safe.
- Missing weather coverage prevents a route from being treated as confirmed-safe.

## Forecast offset behavior

- 0 hours means evaluate the forecast aligned with the planned route timing.
- Positive values shift the weather evaluation forward while preserving the relative checkpoint timing.
- The frontend allows 0–48 hour adjustments and triggers a fresh route request when changed.
- Weather timestamps are requested in UTC and compared against timezone-aware departure and checkpoint times to avoid local-time offset errors across route locations.

## Known limitations

- Real route and weather data require valid API keys and live network access.
- Driver or dispatch decisions should not replace official road status, closures, or emergency instructions.
- Forecast, weather coverage, and ETA values are estimates and may vary materially by route and traffic conditions.
- Generic driving routes are not necessarily truck-legal unless the routing provider explicitly supports the relevant truck restrictions.

## Test commands

Backend:

```powershell
cd .\backend
python manage.py test
```

Frontend:

```powershell
cd .\frontend
npm run test
```

Production build:

```powershell
cd .\frontend
npm run build
```

## Security notes

- Never commit API keys or secret values.
- Keep development secrets in ignored local `.env` files. In production, configure secrets through the hosting platform's private environment settings or a private server-side `.env` file; neither belongs in Git.
- Do not expose ORS credentials in frontend JavaScript.
- Use explicit CORS origins and keep the backend configuration environment specific.
