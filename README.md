# National AHM Projects — Business Development Agent

A private, local-first BD tool for National AHM Projects, a facade and ACP cladding specialist contractor based in Bengaluru.

Purpose: surface active commercial and hospitality construction projects in Bengaluru, maintain a network of developers, consultants, brokers, and site managers who can open doors, and track weekly outbound activity against targets.

## What it does

Three views, one shared data store:

- **Projects** — construction projects discovered from trade press, news, RERA, and architect/engineer portfolios. Filterable by confidence and stage; each project carries a status, activity log, and comment thread.
- **Network** — people and firms who can refer, spec, or introduce: developers, facade consultants, brokers, engineers, site managers, architects. Linked to the projects they touch, tracked independently.
- **Weekly Target** — 30 new projects + 30 new network contacts per week. Live counters for new items, processed items, and activities. Includes a scraper control panel with duplicate-detection and an unprocessed-item guard before re-running.

## Quick start

Requirements: Python 3.10+ (tested on 3.12).

```bash
git clone https://github.com/moinaktardhalayat-beep/ahm-agent.git
cd ahm-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the discovery pipeline once
python3 ahm_scraper/pipeline.py

# Start the dashboard
python3 dashboard/app.py