# LMS — CPNS Quiz Platform

An iPad-first Learning Management System for Indonesian CPNS (Civil Servant) exam preparation.

## Structure

| Directory | Description |
|-----------|-------------|
| `client-ios/` | SwiftUI + PencilKit iPad app |
| `server/` | Rust + Axum REST API |
| `admin-web/` | Next.js admin dashboard |
| `scripts/` | MongoDB setup script |

## Architecture

- **iPad App:** SwiftUI with PencilKit (Apple Pencil drawing per question). Offline-first via SwiftData, syncs with backend when online.
- **Backend:** Rust + Axum + MongoDB. Stateless REST API with JWT auth for admin, device API key for iPad.
- **Admin Web:** Next.js 15 + TypeScript + Tailwind. Create/manage quiz sets and questions, bulk import via JSON.

## CPNS Exam Categories

| Category | Description | Scoring |
|----------|-------------|---------|
| TWK | Tes Wawasan Kebangsaan (National Insight) | Binary: 5 or 0 |
| TIU | Tes Intelejensi Umum (General Intelligence) | Binary: 5 or 0 |
| TKP | Tes Karakteristik Pribadi (Personal Characteristics) | Weighted: 1–5 per option |

## Local Development

```bash
# Backend API
cd server
cargo run

# Admin Dashboard
cd admin-web
npm install && npm run dev

# MongoDB setup (run once)
mongosh "mongodb://localhost:27017/lms" scripts/mongodb_setup.js
```

## Deployment (VPS)

All services self-hosted on Ubuntu VPS:
- nginx as reverse proxy with Let's Encrypt SSL
- Rust binary as systemd service
- Next.js as systemd service (Node.js)
- MongoDB running natively
- Images stored at `/var/lms/uploads/`
