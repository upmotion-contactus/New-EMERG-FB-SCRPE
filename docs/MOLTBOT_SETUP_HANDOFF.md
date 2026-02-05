# MoltBot Setup - Clawdbot Handoff Documentation

## Quick Links
- **MoltBot Setup**: https://pre-deploy-view-1.preview.emergentagent.com/
- **Login**: https://pre-deploy-view-1.preview.emergentagent.com/login

## Overview
MoltBot (OpenClaw) is an AI assistant gateway that provides access to multiple LLM providers through a unified interface.

## Features

### 1. LLM Providers
- **Emergent** (Recommended): Pre-configured with Claude Sonnet 4.5, Claude Opus 4.5, and GPT-5.2 - no API key needed
- **Anthropic**: Bring your own Claude API key
- **OpenAI**: Bring your own OpenAI API key

### 2. Authentication
- Emergent Google OAuth integration
- Instance locking (first user becomes owner)
- Session-based authentication with cookies

### 3. OpenClaw Control UI
- WebSocket-based real-time communication
- Proxy through `/api/openclaw/ui/`
- Token-based gateway authentication

## API Endpoints

### Auth APIs
```
GET  /api/auth/instance    - Check if instance is locked
POST /api/auth/session     - Exchange session_id for token
GET  /api/auth/me          - Get current user
POST /api/auth/logout      - Logout and clear session
```

### OpenClaw APIs
```
POST /api/openclaw/start   - Start gateway {provider, apiKey?}
GET  /api/openclaw/status  - Get gateway status
POST /api/openclaw/stop    - Stop gateway (owner only)
GET  /api/openclaw/token   - Get gateway token (owner only)
GET  /api/openclaw/ui/*    - Proxy to Control UI
WS   /api/openclaw/ws      - WebSocket proxy
```

## Key Files

### Backend
- `/app/backend/server.py` - Main server with all endpoints
- `/app/backend/gateway_config.py` - Gateway env configuration
- `/app/backend/supervisor_client.py` - Supervisor process management
- `/app/backend/whatsapp_monitor.py` - WhatsApp status monitoring

### Frontend
- `/app/frontend/src/pages/LoginPage.js` - Google OAuth login
- `/app/frontend/src/pages/SetupPage.js` - Provider selection and start
- `/app/frontend/src/pages/AuthCallback.js` - OAuth callback handler

### Configuration
- `~/.clawdbot/clawdbot.json` - Gateway configuration
- `/app/backend/.env` - Backend environment variables
- `/app/frontend/.env` - Frontend environment variables

## Usage Instructions

### To Start MoltBot:
1. Go to `/` (or `/login` if not authenticated)
2. Login with Google account
3. Select LLM provider (Emergent recommended)
4. Click "Start OpenClaw"
5. Redirected to Control UI automatically

### Environment Variables
```
# Backend (.env)
MONGO_URL=mongodb://...
DB_NAME=moltbot_app
EMERGENT_API_KEY=sk-emergent-...
EMERGENT_BASE_URL=https://integrations.emergentagent.com/llm

# Frontend (.env)
REACT_APP_BACKEND_URL=https://...
```

## Tech Stack
- **Backend**: FastAPI + MongoDB
- **Frontend**: React + TailwindCSS
- **Gateway**: Clawdbot (Node.js)
- **Process Manager**: Supervisor

## Ports
- Frontend: 3000
- Backend: 8001
- Gateway: 18789 (internal)

## Tutorial
https://emergent.sh/tutorial/moltbot-on-emergent
