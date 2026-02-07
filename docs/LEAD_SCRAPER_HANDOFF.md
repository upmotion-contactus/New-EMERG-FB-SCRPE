# Lead Scraper - Clawdbot Handoff Documentation

## Quick Links
- **Lead Scraper Dashboard**: https://scraper-rebuild.preview.emergentagent.com/scraper
- **Scrape Database**: https://scraper-rebuild.preview.emergentagent.com/scrapes
- **MoltBot Setup**: https://scraper-rebuild.preview.emergentagent.com/

## Overview
Multi-Industry Facebook Group Lead Scraper built on MoltBot platform.

## Features

### 1. Lead Scraper (`/scraper`)
- **6 Industries**: Plumbing, HVAC, Electrical, Remodeling, Landscaping, Power Washing
- **Facebook Cookie Auth**: Paste cookies from browser extension (EditThisCookie/Cookie-Editor)
- **Auto Industry Detection**: Detects industry from Facebook group URL
- **Infinite Scroll Scraping**: Collects all visible members
- **Deep Profile Scraping**: Extracts phone, website, address from profiles
- **Real-time Progress**: Benchmark progress bar (50-member segments)
- **Job History**: Track past scraping jobs

### 2. Scrape Database (`/scrapes`)
- **File Management**: Upload, download, delete CSV files
- **Auto-Tagging**: Files tagged by industry keywords
- **Search & Filter**: Find files by name or tag
- **Quick Download Links**: Shareable direct download URLs

## API Endpoints

### Scraper APIs
```
GET  /api/scraper/industries          - List supported industries
POST /api/scraper/detect-industry     - Auto-detect industry from text
GET  /api/scraper/cookies/status      - Check if cookies configured
POST /api/scraper/cookies/save        - Save Facebook cookies (JSON array)
DEL  /api/scraper/cookies             - Delete saved cookies
POST /api/scraper/start               - Start scraping job {urls: [], industry: string}
GET  /api/scraper/job/{job_id}        - Get job status
POST /api/scraper/job/{job_id}/stop   - Stop running job
GET  /api/scraper/jobs                - List job history
```

### File Management APIs
```
GET  /api/scrapes                     - List all CSV files with metadata
POST /api/scrapes/upload              - Upload CSV file (multipart/form-data)
GET  /api/scrapes/download/{filename} - Download specific file
DEL  /api/scrapes/{filename}          - Delete specific file
```

## Key Files

### Backend
- `/app/backend/server.py` - Main FastAPI server with all endpoints
- `/app/backend/fb_scraper.py` - Playwright scraping logic
- `/app/backend/industry_config.py` - Industry keywords configuration

### Frontend
- `/app/frontend/src/App.js` - Router with /scraper and /scrapes routes
- `/app/frontend/src/pages/ScraperDashboard.jsx` - Lead scraper UI
- `/app/frontend/src/pages/ScrapeDashboard.jsx` - File management UI

### Data Storage
- `/app/scrape_files/` - CSV files stored here
- `/app/backend/fb_cookies.json` - Facebook cookies (when configured)
- MongoDB `scraper_jobs` collection - Job history

## Usage Instructions

### To Start Scraping:
1. Go to `/scraper`
2. Click Settings icon next to "Facebook Cookies"
3. Paste cookies JSON array from browser extension
4. Click "Save Cookies"
5. Select industry from dropdown
6. Enter Facebook group URLs (one per line)
7. Click "Start Scraping"

### Cookie Format (JSON array):
```json
[
  {"name": "c_user", "value": "...", "domain": ".facebook.com"},
  {"name": "xs", "value": "...", "domain": ".facebook.com"},
  ...
]
```

## Tech Stack
- **Backend**: FastAPI + MongoDB + Playwright
- **Frontend**: React + TailwindCSS + Framer Motion
- **Browser**: Chromium via Playwright

## Security Notes
- Slug generation uses 64 bits of entropy (secrets.token_hex(8))
- Cookies stored server-side only
- No credentials in URLs
