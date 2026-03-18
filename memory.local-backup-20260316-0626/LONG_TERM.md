# Project Long Term Memory: Beauty-PK

## 📜 Core Rules
- **Tech Stack**: Next.js 16 (App Router), Supabase, Tailwind CSS v4, Framer Motion.
- **Design System**: Glassmorphism, Premium Aesthetics, Cyberpunk influences.
- **Database**: PostgreSQL (Supabase) - Tables: users, photos, votes, transactions.

## 🏗️ Architecture
- **Auth**: Supabase Auth (Google OAuth only for production/premium feel).
- **Backend**: API Routes in Next.js (`app/api/`) + Supabase Service Role for admin tasks.
- **Voting**: ELO Rating System (K-factor 32).

## ✅ Past Milestones
- [x] Project Foundation & DB Setup.
- [x] Photo Upload & Gallery (S3 storage).
- [x] Core PK System (Voting & ELO).
- [x] Leaderboard Foundation.
