# Veritas web app

The website people use to give through Veritas, and that charities and other organisations
use to raise money for their projects. Nobody has to install anything: it runs in the
browser on a phone or a computer.

- **Donors** browse causes and projects, see on a map of Azerbaijan where money is going,
  follow each project's milestones and evidence, and give once or "pay on proof" (the
  money moves only when a milestone is shown to be done). In their portfolio, each project
  opens to show what they gave and where it is now, milestone by milestone, the proof
  behind each milestone and how its donors voted, their own vote included.
- **Organisations** (registered charities and public unions, not individuals) apply with
  their legal details and documents. Once Veritas has checked them, they plan a project
  (its stages, each stage's budget, the proof that will release its money, the contractor,
  the officer and the site), publish it, and follow its money, proof and votes.
- **Both** can export their portfolio, or one project, as a PDF report or an Excel workbook.
- **Anyone** can open a project's proof before giving (the site photos, every document and
  the donors' votes), and read on `/how-it-works` how each step is checked, from verifying
  the organisation to recording the payment on the blockchain.

React 18, TypeScript, Vite, Tailwind CSS with shadcn/ui, Framer Motion, React Router and
TanStack Query. Accounts are the Veritas API's own: an email and a password it checks
itself, or "Continue with Google" through Firebase.

## Running it

You need Node.js 20 or newer (22 is what the Dockerfile uses).

```bash
cd frontend
npm install
cp .env.example .env.local   # optional: only Google sign-in needs values in it
npm run dev                  # http://localhost:8080
```

Signing up and signing in need the API: start it as the [backend readme](../backend/README.md)
says (`uv run uvicorn veritas.api.app:create_app --factory`, port 8000). The dev server passes
`/v1` and `/health` through to it, so there is nothing else to set; if your API runs elsewhere,
set `VERITAS_API_PROXY` in `.env.local`. Without the API the public pages still work on their
sample data, and a signed-in console says it is offline.

| command | what it does |
|---|---|
| `npm run dev` | dev server with hot reload on port 8080 |
| `npm run build` | production build into `dist/` |
| `npm run preview` | serve the production build |
| `npm run typecheck` | TypeScript, no output |
| `npm run lint` | ESLint |

## Sign-in

**Email and password** is the API's own: `POST /v1/auth/signup` and `POST /v1/auth/login`.
The API keeps passwords only as salted scrypt hashes, stops password logins to an account
for a while after too many wrong ones, and sends a one-time link to set a new password
(`/forgot-password`, then `/reset-password#token=…` from the email). In development the API
writes that email to its log instead of sending it (`VERITAS_MAIL_ECHO=true`); in production
it needs an SMTP server (`VERITAS_SMTP_*`, see `backend/.env.example`). Settings changes the
password, and ends the account's other sessions when it does.

**Continue with Google** is the one part that uses Firebase, and the button only appears
when the Firebase web config is set:

1. Create a project in the [Firebase console](https://console.firebase.google.com).
2. Authentication → Sign-in method: turn on **Google**.
3. Authentication → Settings → Authorized domains: `localhost` is there already; add the
   domain the site will run on.
4. Project settings → Your apps: add a web app and copy its `apiKey`, `authDomain`,
   `projectId` and `appId` into `VITE_FIREBASE_*` in `.env.local`. These name the project
   and grant nothing on their own, so they may be in the built site.
5. Give the backend the same project id: `VERITAS_FIREBASE_PROJECT_ID` in `backend/.env`.

Firebase signs the person in to Google and gives the app an ID token; the app sends it to
`POST /v1/auth/firebase`, where the API checks Google's signature, the project and the
expiry. If the email already has a Veritas account, Google is joined to it (and, since
nobody proved who chose that account's password, the password is dropped and its sessions
end; it can be set again by email). Then the app signs out of Firebase: from here on it is
an ordinary Veritas session.

**Demo accounts**: the sign-in and sign-up pages have **Demo donor** and **Demo
organisation** buttons that sign in with one click, with no email or password, through
`POST /v1/auth/demo`. The API allows that only with `VERITAS_DEMO_LOGIN=true` (on in
`backend/.env.example`; on a public server, only for a demo), and the buttons say so when
it is off.

- The demo donor is `admin@gmail.com`, which also signs in with the password `admin1234`
  once the backend's `scripts/seed_demo.py` has made it (or put it back). Like every
  account, it shows the sample portfolio until it has donations of its own.
- The demo organisation is First Steps Children's Fund, already verified, with a verified
  contractor and a Verification Officer, so it can plan and publish a project at once.

Either way the API answers with a session token, which the app keeps in `localStorage`, so
the sign-in lasts across reloads and tabs until it expires (30 days by default) or the
person signs out, which ends it on the API too.

Choosing "Donor" or "Organisation" happens once, at sign-up or right after the first
Google sign-in. An organisation then fills in its application (legal name, VÖEN, legal
form, address, director, contacts and documents), which is sent to `POST /v1/charities`.
If the API cannot be reached, the application is kept in the browser and can be sent later.

Veritas then checks it (the state register, the VÖEN with the tax service, the director's
ID and the bank account) and verifies the organisation, or sends it back with a note on
what to change. The Projects page shows which step the organisation is at. A Veritas admin
does this through the API (`POST /v1/charities/{id}/verify`, `/reject` or `/suspend`); the
web app has no reviewer screen yet.

A verified organisation plans a project in six steps at `/organisation/projects/plan/:id`:
the project; its stages, each with its work, dates and budget lines; the photos and
documents that will prove each stage; the contractor and the Verification Officer; and the
site. The draft is saved to `PUT /v1/projects/{id}/passport` as you type, and what the API
says is still missing shows on the step it belongs to. Publishing (`POST
/v1/projects/{id}/publish`) fixes the plan as the project's Passport and shows its
fingerprint and IPFS address. "Fill in an example" writes a complete project to try it.

## What is real and what is sample

The backend does not have public project listings, a map feed or card payments from the
web yet, so some pages run on sample data. Everything sample says so on the page.

| | where it comes from |
|---|---|
| sign-up, sign-in, passwords, account, display name | the API (Google through Firebase) |
| organisation application and its status | the API (`/v1/charities`), or a draft in the browser while it is offline |
| your donations | the API (`/v1/donations`) once you have given; until then, and while the API is out of reach, a sample portfolio every account starts with |
| causes, projects, organisations, milestones, evidence | `src/data/` (sample): 26 projects at every stage, two of them in Ukraine and one stopped |
| each milestone's proof documents, checks, officer's decision and donor vote | `src/data/sample-proof.ts` (sample), made from the sample projects the same way every time |
| the site photos of the finished school in Gəncə | `public/img/proof/` (sample): photos of other buildings from Wikimedia Commons, credited in `public/img/README.md` |
| an organisation's own projects, drafts and published | the API (`/v1/charities/{id}/projects`, `/v1/projects`) |
| the example projects beside them | a sample organisation's |
| the map's numbers | worked out from the sample projects |
| giving | a preview of the steps; it does not take a card yet |
| PDF and Excel exports | written in the browser from what the page shows; nothing is sent anywhere |

Money is always whole qəpik (1 ₼ = 100 qəpik), as in the backend; only `src/lib/money.ts`
formats it.

## Where things are

```
src/
  pages/          one file per route (App.tsx lists them)
  components/
    lp/           the landing page: curved photo cards, product mock-ups, the map band
    donate/       project cards, milestone timeline, the giving sheet
    proof/        a milestone's photos full size and its documents as pages, to open
    map/          the interactive map of Azerbaijan and its data
    console/      the signed-in area: organisation status
    portfolio/    the export menu, and the look of a project in a portfolio
    layout/       side rail, top bar and mobile bar of the signed-in area
    auth/         the sign-in pages' frame
    tour/         the guided tours
    ui/           shadcn/ui building blocks
  contexts/       AuthContext: the API session, Google through Firebase, the account type
  data/           sample causes, regions, projects, account, proof and votes
  lib/            the API client, Firebase, money, the organisation draft, the project
                  planner's Passport, the portfolio
    export/       the PDF and Excel writers and the report they write
  styles/         page styles on top of Tailwind
```

### Exports

The Export button on the dashboard, on My donations, on an organisation's Projects and on
each project in a portfolio offers two files:

- **PDF report**: the totals and where the money is, every project, every donation, and
  for each milestone its money, its proof (photos, capture manifest, invoice, e-kassa
  receipt, each with its SHA-256 fingerprint, the IPFS folder of the blurred photos and the
  Polygon transaction), the 11 checks, the officer's decision and the donors' vote.
- **Excel workbook**: the same as numbers and dates you can sort, filter and add up, one
  sheet each for the summary, projects, donations, milestones, proof, checks and votes.

Both are made in the browser by `src/lib/export/` without any library: `pdf.ts` writes the
PDF and embeds Roboto (`public/fonts/`, Apache License 2.0, with its licence) so that ə, ş,
ğ and ₼ print as they look on screen, and `xlsx.ts` writes the workbook's XML and zips it.
The fonts are fetched only when someone exports a PDF.

### The map

`components/map/AzMap.tsx` draws Azerbaijan's 14 economic regions (the 2021 division) as an
SVG choropleth in the site's colours, with a pin per project. Hover or tap a region for its
numbers, click it to zoom in and list its projects, drag to pan, and use the wheel or the
buttons to zoom. It works with the keyboard too. `/map` is the full page, with a filter by
cause; the landing page has a smaller copy.

The outlines in `components/map/az-regions.ts` come from geoBoundaries' AZE ADM2 boundaries
(based on Wikipedia data, CC BY-SA 3.0): the 79 districts and cities were tagged with their
economic region, merged with mapshaper, simplified and projected. That file is shared under
CC BY-SA 3.0 as well. Regenerate it rather than editing the paths.

### Pictures

The photographs are from Unsplash, under the Unsplash licence. `public/img/README.md` lists
each one. They illustrate causes and do not show real Veritas projects.

## Deploying

- **One server (for example a Contabo VPS) with Docker**: `docker build -t veritas-web .`
  builds the site and serves it with nginx. `nginx.conf` passes `/v1/` and `/health` to
  `http://api:8000`, so run it next to the API container under the name `api`: the app and
  the API share one origin and need no CORS. Put TLS in front (a reverse proxy with Let's
  Encrypt), set the backend's `VERITAS_WEB_APP_URL` to the site's address and its
  `VERITAS_SMTP_*` for the password emails, and rate-limit `/v1/auth/` there too: every
  password check costs real CPU, by design.
- **A static host** (Vercel, with `vercel.json`, or any other): the host cannot pass `/v1`
  through, so set `VITE_API_URL` to the API's address when building, and add the site's
  origin to the backend's `VERITAS_CORS_ORIGINS`.

With Google sign-in on, add the site's domain to Firebase's authorized domains.
