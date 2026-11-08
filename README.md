# National AHM Projects — Business Development Agent

A private, local-first BD tool for National AHM Projects, a facade and ACP cladding specialist contractor based in Bengaluru.

Purpose: surface active commercial and hospitality construction projects in your target cities, maintain a network of developers, consultants, brokers, and site managers who can open doors, and track weekly outbound activity against targets.

## Architecture

- **Local Mac:** The engine. Runs the web scrapers, processes data, and holds the local JSON files for testing.
- **GoDaddy Cloud:** The database and live dashboard. Runs FastAPI and MySQL, accessible to the whole team.

## What it does

Three views, one shared data store:

- **Projects** — construction projects discovered from trade press, news, RERA, and architect/engineer portfolios. Filterable by confidence and stage; each project carries a status, activity log, and follow-up dates.
- **Network** — people and firms who can refer, spec, or introduce: developers, facade consultants, brokers, engineers, site managers, architects. Linked to the projects they touch, tracked independently.
- **Weekly Target** — A sales dashboard showing this week's meetings, to-do list (follow-ups due), recent activity, and last week's done list. Data is filtered by team member (Admin sees all, members see their own).

---

## 🚀 The 3 Magic Scripts (Mac Workflow)

Make sure you are in the project root (`~/AHM/agent/ai-agent-freelancer`) and your virtual environment is active (`source .venv/bin/activate`).

### 1. Pull Data from GoDaddy (Sync DOWN)
If you or your team (Kartik/Saad) have logged activities, changed statuses, or added projects on the live site, run this to download all the latest data to your Mac's JSON files.
```bash
python3 pull_from_db.py

2. Generate New Leads (Scrape)
Run your web scrapers to find new projects and network contacts. You can now target specific cities. This script merges new leads into your existing phase0_leads.csv without overwriting data from other cities.

To scrape Bengaluru:

bash
python3 ahm_scraper/pipeline.py --city Bengaluru
To scrape Goa:

bash
python3 ahm_scraper/pipeline.py --city Goa
3. Upload to GoDaddy (Sync UP)
Once you have new scraped leads or local changes, run this to push everything securely over HTTPS to the live GoDaddy database.

bash
python3 sync_to_db.py
Typical Weekly Flow:
Pull -> Scrape -> Sync Up

💻 Running Locally
To test UI changes or view the dashboard locally without affecting the live site:

Open dashboard/db_config.py and ensure LOCAL_MODE = True.

Start the local server:

bash
python3 dashboard/app.py
Open http://localhost:8500.

(To push changes to GoDaddy, upload the modified files and set LOCAL_MODE = False in GoDaddy's db_config.py).

Data Model
Every project and network contact carries a confidence label — Verified, Reported, Inference, or Unknown — never silently upgraded. A project is not a qualified lead until fit and timing are reasonably verified AND a contact path is identified.

Project fields: name, location, sector, owner/developer, operator/brand, architect/consultant, main contractor/PM, stage and stage evidence date, total project value, potential AHM package value (kept distinct), facade/ACP scope evidence, package award status (OPEN / AWARDED / PARTIAL / UNKNOWN — never assumed), decision-maker, contact source, referral path, confidence label, lead stage.

Network fields: name, type, firm, role in firm, how they help, phone, WhatsApp, email, LinkedIn, website, source, relationship (cold / warm / referred), linked lead keys, last contacted, next action, next action due.

Both are cross-referenced but independently editable.

Working principles
Bengaluru and Goa focus. Commercial buildings and hotels/hospitality.

AHM scope: facade and ACP cladding. Target package value: INR 10 lakh – INR 10 crore.

No tender/RFQ requirement — private, relationship-led work is the primary channel.

Quality over quantity. Twenty well-researched opportunities beats a thousand generic contacts.

Do not presume a facade package is still open just because a project is ongoing.

Distinguish Verified / Reported / Inference / Unknown. Never promote an inference to a fact.

Discovery sources
Biltrax Media — per-project trade press pages

Facade-focused news — real project names extracted from article bodies

Google News RSS — filtered dynamically for the target city + sector + action keyword.

Architect sites — design portfolios where facade/ACP is evidenced

Developer Sites — pulls corporate phone and email contacts into the Network tab automatically.

Architecture
text
ahm_scraper/          discovery pipeline + sources
  sources/            individual scrapers
  models.py           ProjectRecord schema
  extract.py          shared field-extraction & city-filter utilities
  pipeline.py         merge, quality-gate, dedupe, write CSV
  output/             leads CSV, state JSON, rejected log

dashboard/            FastAPI + Jinja2 local dashboard
  app.py              routes, scraper endpoints
  data.py             storage layer (Local JSON <-> MySQL)
  auth.py             password hashing & sessions
  templates/          Projects, Network, Weekly views
Environment
Create a .env file for secrets (not tracked in git):

env
AHM_SESSION_SECRET=your_secure_random_string
License
Private. All rights reserved. National AHM Projects.