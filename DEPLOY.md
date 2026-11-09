# Deploying Veritas

The prototype is live at **[https://veritas.173.212.195.158.sslip.io](https://veritas.173.212.195.158.sslip.io)**. This page explains how it runs there and how to put it on another server.

## What runs

Three containers, started by [docker-compose.yml](docker-compose.yml), behind the server's own nginx:

```
browser ──HTTPS──> host nginx (TLS from Let's Encrypt)
                      │
                      └─> 127.0.0.1:8110  web   nginx serving the React build
                                             │   and passing /v1 and /health on
                                             └─> api   FastAPI on :8000
                                                    │
                                                    └─> db   PostgreSQL 17 + PostGIS
```

| Container | Built from | What it does |
|---|---|---|
| `web` | [frontend/Dockerfile](frontend/Dockerfile) | Builds the web app with Vite and serves it with nginx ([frontend/nginx.conf](frontend/nginx.conf)). API calls go to the same address, so the browser needs no CORS. |
| `api` | [backend/Dockerfile](backend/Dockerfile) | On every start ([docker-entrypoint.sh](backend/docker-entrypoint.sh)): runs the database migrations, resets the judges' account `admin@gmail.com` / `admin1234`, then serves the API with two uvicorn processes. |
| `db` | `postgis/postgis:17-3.5` | The database. Its data lives in the `db-data` volume and survives restarts and rebuilds. |

Only the web container is published, and only on `127.0.0.1`, so nothing reaches the API or the database except through nginx.

### What the demo leaves out

The demo runs with `VERITAS_ENV=dev` and **no blockchain**, because production mode refuses to start without one. So:

- organisations can publish a Passport, but it never launches on-chain;
- the relayer, indexer and evidence workers are not running, and neither are the mock card provider and bank;
- reset-password emails are written to the API's log (`VERITAS_MAIL_ECHO`), as there is no SMTP server.

The donor dashboard, the project pages and their proof, the map and the portfolio run on the web app's **sample data**, which is labelled on every screen. Sign-up, sign-in, the demo buttons, Google sign-in and the assistant use the real API and database.

## Deploy on a new server

You need a Linux server with Docker (with the compose plugin), `make`, nginx and certbot, and ports 80 and 443 open.

**1. Get the code.**

```bash
git clone https://github.com/eminroot/veritas.git /opt/veritas
cd /opt/veritas
```

**2. Settings.** `make env` makes `.env` (the database password) and `deploy/veritas.env` (the API's settings) from the examples, with random secrets. Then edit `deploy/veritas.env`:

| Setting | Set it to |
|---|---|
| `VERITAS_WEB_APP_URL` | the site's address, e.g. `https://veritas.173.212.195.158.sslip.io` |
| `VERITAS_OPENAI_API_KEY` | an OpenAI key, for the assistant. Empty: the assistant says it is off |
| `VERITAS_FIREBASE_PROJECT_ID` | the Firebase project, for "Continue with Google". Empty: that button is refused |

For the Google button to show at all, the web app needs its Firebase config at build time: copy `frontend/.env.example` to `frontend/.env.local` and fill in the four `VITE_FIREBASE_*` values. Without it everything else works.

Both env files are in `.gitignore`. Never commit them.

**3. Start it.**

```bash
make up       # builds the images and starts the containers, a few minutes the first time
make health   # web 200 and {"status":"ready",...} when all is well
```

**4. A domain, for free.** [sslip.io](https://sslip.io) answers any name that ends in the server's IP with that IP, so `veritas.<server-ip>.sslip.io` works with no DNS setup. Add an nginx site for it, `/etc/nginx/sites-available/veritas.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name veritas.173.212.195.158.sslip.io;

    client_max_body_size 25M;   # evidence photos and KYB documents

    location / {
        proxy_pass http://127.0.0.1:8110;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }
}
```

`X-Forwarded-For` is set, not appended, so a visitor cannot pick the address the API sees. The assistant's rate limit counts per address.

**5. HTTPS.** Enable the site and let certbot add the certificate and the redirect from HTTP:

```bash
ln -s /etc/nginx/sites-available/veritas.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d veritas.173.212.195.158.sslip.io --non-interactive --agree-tos --redirect
```

Certbot renews the certificate by itself.

**6. Google sign-in.** In the Firebase console, add the domain under Authentication, Settings, Authorized domains.

## Everyday commands

Run them in `/opt/veritas`. `make help` lists them all.

| Command | What it does |
|---|---|
| `make up` | Rebuild and restart what changed, after new code. The database is kept |
| `make ps` | The containers and their health |
| `make logs-api` | Follow the API's log |
| `make health` | Check the site, the API and the database |
| `make seed` | Reset the judges' account, if someone changed its password |
| `make psql` | A database shell |
| `make down` | Stop and remove the containers. The data volumes stay |

## Our server

| | |
|---|---|
| Address | https://veritas.173.212.195.158.sslip.io |
| Server | Contabo VPS, Ubuntu 24.04, 4 vCPU, 8 GB RAM |
| Code | `/opt/veritas`, uploaded from a checkout with `frontend/.env.local` in it (for Google sign-in). After new code: upload it again, then `make up` |
| Web container | `127.0.0.1:8110`, behind the host's nginx |
| Settings | `/opt/veritas/.env` and `/opt/veritas/deploy/veritas.env`, on the server only |

The server also hosts two of our other projects, each on its own port behind the same nginx. They are stopped while the jury tests Veritas, so it has the whole machine.

## When something is wrong

| You see | Look at |
|---|---|
| `502 Bad Gateway` | `make ps`: the `web` container is down. `make up` starts it again |
| The site loads, but sign-in fails | `make logs-api` and `make health`: the API or the database |
| The demo password stopped working | `make seed` |
| The assistant says it is off | `VERITAS_OPENAI_API_KEY` in `deploy/veritas.env`, then `make up` |
| "Continue with Google" fails | The domain in Firebase's authorized domains, step 6 |
