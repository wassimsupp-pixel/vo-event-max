# VO Event Max

## Architecture
```
vo-event-max/
├── apps/
│   ├── web/        → Next.js 14 + TypeScript + Tailwind + shadcn/ui (Vercel)
│   └── api/        → FastAPI + Python (Railway EU Amsterdam)
├── packages/
│   └── matching-engine/  → Isolated Python matching module
└── docs/
    └── schema.sql  → PostgreSQL DDL (Supabase Paris eu-west-3)
```

## Stack
- **Frontend**: Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: FastAPI (Python 3.12)
- **Database**: PostgreSQL via Supabase (Paris, eu-west-3)
- **Auth**: Supabase Auth
- **Storage**: Supabase Storage (private bucket, signed URLs only)
- **Frontend hosting**: Vercel
- **API hosting**: Railway (Amsterdam, EU)
- **i18n**: next-intl (FR / NL / EN)

## Quick Start

### Prerequisites
- Node.js 20+
- Python 3.12+
- uv or pip

### Frontend (apps/web)
```bash
cd apps/web
cp .env.example .env.local   # fill in Supabase credentials
npm install
npm run dev
```

### API (apps/api)
```bash
cd apps/api
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload
```

### Matching Engine (standalone test)
```bash
cd packages/matching-engine
pip install -r requirements.txt
python synthetic_data.py          # generate test data
python -m pytest tests/ -v --cov=.
```

## Environment Variables
See `.env.example` at the root. Each sub-app has its own `.env.example`.

## RGPD / Security
- All storage: private Supabase bucket, signed URLs (1h expiry)
- RLS enabled on all database tables
- `dietary_requirements` field: restricted to admin/pm roles via RLS
- Hosting: 100% EU (Supabase Paris + Railway Amsterdam + Vercel Edge)
- No real client data until RGPD validation (Timelex) confirmed

## Phase 1 Scope
- ✅ Auth & roles (admin / pm / client / viewer)
- ✅ Event & project creation
- ✅ File import (Excel/CSV) with column mapping
- ✅ Matching engine (deterministic, rule-based, no ML/AI)
- ✅ Exception detection & management
- ✅ Non-destructive re-merge
- ✅ Audit trail (change_log)
- ✅ Excel export (multi-sheet)
- ✅ Dashboard UI

## Phase 2 (not yet built)
Flights view, Hotels, Transfers, Activities, Client portal, Reporting

## Phase 3 (future)
Email Agent, AI-assisted communications, Smart checklists
