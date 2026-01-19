# VibeRooms

## Project Overview
VibeRooms is a full-stack web application that generates collaborative Spotify playlists by aggregating group music preferences. It uses a scoring-based recommendation engine to rank tracks and create playlists that reflect the shared vibe of a room.

## Tech Stack
- Backend: FastAPI (async), SQLAlchemy, JWT
- Auth: Spotify OAuth 2.0
- Database: SQLite (PostgreSQL-ready)
- APIs: Spotify Web API
- Frontend: React

## Current Status
✅ Spotify OAuth login and token refresh  
✅ JWT-based application authentication  
✅ User, room, and room membership models  
✅ Preference submission per user  
✅ Aggregation into a room-level vibe profile  
✅ Scoring-based playlist generation logic  
✅ Async FastAPI backend with clean service separation  

## In Progress / Next Steps
⬜ Spotify track fetching and candidate song pool generation  
⬜ Fine-tuning scoring weights and constraints  
⬜ Playlist creation and save-to-Spotify flow  
⬜ Frontend UI polish and edge-case handling  
⬜ Deployment and final testing  

## Architecture / Flow
User → Spotify OAuth → Room Creation  
→ Preference Submission → Vibe Profile Aggregation  
→ Scoring Engine → Ranked Tracks → Spotify Playlist
