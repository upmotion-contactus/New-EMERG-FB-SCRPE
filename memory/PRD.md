# MoltBot + Lead Scraper PRD

## Original Problem Statement
Multi-Industry Facebook Group Lead Scraper with MoltBot AI assistant integration. Users scrape Facebook groups for business contacts across multiple industries, with cookie-based auth, CSV export, and file management.

## Architecture
- **Backend**: FastAPI (Python) with MongoDB
- **Frontend**: React with TailwindCSS, Shadcn UI
- **Browser Automation**: Playwright for Facebook scraping
- **MoltBot Integration**: OpenClaw AI assistant gateway

## User Personas
1. **Lead Generator**: Sales professionals scraping Facebook groups for business contacts
2. **Marketing Teams**: Collecting leads across multiple industries for outreach campaigns

## Core Requirements
- Multi-industry support (8 industries: Plumbing, HVAC, Electrical, Remodeling, Landscaping, Power Washing, Roofing, Painting)
- Facebook cookie-based authentication with expiration awareness
- Infinite scroll scraping with progress tracking
- Single CSV file per scrape job (no duplicate/checkpoint files)
- File management dashboard with search/filter/download/delete
- Non-duplicate completion notifications

## What's Been Implemented

### Backend APIs
- `GET /api/scraper/industries` - List supported industries
- `POST /api/scraper/detect-industry` - Auto-detect industry from text
- `GET /api/scraper/cookies/status` - Check cookie config + expiration status
- `POST /api/scraper/cookies/save` - Save Facebook cookies
- `DELETE /api/scraper/cookies` - Delete cookies
- `GET /api/scraper/browser/status` - Check Playwright browser availability
- `POST /api/scraper/start` - Start scraping job
- `GET /api/scraper/job/{job_id}` - Get job status
- `POST /api/scraper/job/{job_id}/stop` - Stop job
- `GET /api/scraper/jobs` - List job history (with stale job cleanup)
- `POST /api/scraper/jobs/cleanup` - Manual cleanup of stuck jobs
- `GET /api/scrapes` - List CSV files with metadata
- `POST /api/scrapes/upload` - Upload CSV
- `GET /api/scrapes/download/{filename}` - Download CSV
- `DELETE /api/scrapes/{filename}` - Delete CSV
- `GET /api/leads` - Get all leads from DB with filters
- `POST /api/leads/import-from-csv/{filename}` - Import CSV to DB

### Frontend Pages
- `/scraper` - Lead Scraper Dashboard (industry selector, cookie config with expiration warnings, URL input, live progress, job history with download)
- `/scrapes` - Lead Database (file listing, search/filter by industry, upload/download/delete)

### Key Files
- `/app/backend/server.py` - Main API server
- `/app/backend/fb_scraper.py` - Playwright scraping logic (stable Feb 6th version)
- `/app/backend/industry_config.py` - Industry keywords
- `/app/frontend/src/pages/ScraperDashboard.jsx` - Scraper UI
- `/app/frontend/src/pages/ScrapeDashboard.jsx` - Lead database UI

### Housekeeping Features (Completed Dec 2025)
- Cookie expiration checking with frontend warnings (amber/red banners)
- Single CSV file per scrape job (no checkpoint files)
- completionNotified flag prevents duplicate toast notifications
- Stale job auto-cleanup (jobs running > 4 hours marked as stale)

## Prioritized Backlog

### P1 (High)
- Modularize `fb_scraper.py` for better maintainability
- Consolidate job state from in-memory dict to MongoDB `jobs` collection

### P2 (Medium)
- Export to CRM formats
- Scheduled scraping jobs
- Duplicate lead detection across files
