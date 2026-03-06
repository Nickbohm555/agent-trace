2. Stack: Docker Compose + FastAPI + React/TypeScript/Vite + Postgres + Alembic + pgvector.
2. Always use react for frontend, not html
3. Source roots: `src/backend/`, `src/frontend/`, and `docker-compose.yml`.
4. Backend dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`).
6. Build all services: `docker compose build`.
7. Start all services: `docker compose up -d`.
8. Refresh (normal iteration): Restart backend to pick up code changes: `docker compose restart backend`. No need to tear down or rebuild unless you change dependencies or Dockerfile.
9. Start fresh (when needed): Remove all services, volumes, and images: `docker compose down -v --rmi all`, then `docker compose build` and `docker compose up -d`.
10. Service names: `db`, `backend`, `frontend`.
10. Host port map (must stay distinct from agent-search): `db=5433`, `backend=8001`, `frontend=5174`, `chrome=9223`.
11. Frontend URL: `http://localhost:5174`.
12. Backend URL: `http://localhost:8001`.
13. Backend readiness endpoint (current scaffold): `http://localhost:8001/docs`.
15. Tail all logs: `docker compose logs -f`.
16. Tail backend logs - also use for backend checks: `docker compose logs -f backend`.
17. Tail frontend logs: `docker compose logs -f frontend`.
18. Tail DB logs: `docker compose logs -f db`.
19. Show running state: `docker compose ps`.
20. Backend shell: `docker compose exec backend sh`.
21. Frontend shell: `docker compose exec frontend sh`.
22. DB shell: `docker compose exec db psql -U ${POSTGRES_USER:-agent_user} -d ${POSTGRES_DB:-agent_trace}`.
23. Alembic upgrade: `docker compose exec backend uv run alembic upgrade head`.
24. Create migration: `docker compose exec backend uv run alembic revision -m "describe_change"`.
25. Alembic history: `docker compose exec backend uv run alembic history`.
26. Alembic current: `docker compose exec backend uv run alembic current`.
27. Verify pgvector extension: `docker compose exec db psql -U agent_user -d agent_trace -c "\\dx"`.
28. Verify tables: `docker compose exec db psql -U agent_user -d agent_trace -c "\\dt"`.
29. Wipe internal data (documents + chunks only): `POST /api/internal-data/wipe` or `docker compose exec db psql -U agent_user -d agent_trace -c "TRUNCATE internal_documents CASCADE;"`.
30. Backend tests: `docker compose exec backend uv run pytest`.
31. Backend smoke tests: `docker compose exec backend uv run pytest tests/api -m smoke`.
32. Frontend tests: `docker compose exec frontend npm run test`.
33. Frontend typecheck: `docker compose exec frontend npm run typecheck`.
34. Frontend build check: `docker compose exec frontend npm run build`.
35. Browser debug workflow for E2E feature testing:
- Start app services: `docker compose up -d backend frontend`.
- Stop Docker Chrome if it occupies debug port: `docker compose stop chrome`.
- One-command setup + launch: `./chromeDev`.
- `chromeDev`/`launch-devtools.sh` is not a one-time setup command; run it whenever you want to start a new local Chrome DevTools session.
- If port `9223` is already in use and `curl http://127.0.0.1:9223/json/list` returns targets, reuse that active session instead of relaunching.
- Launch debug browser: `./launch-devtools.sh http://localhost:5174`.
- DevTools targets endpoint: `http://127.0.0.1:9223/json/list`.
- Verify debug endpoint: `curl http://127.0.0.1:9223/json/list` (expect JSON with targets and `webSocketDebuggerUrl`).
- Keep the Chrome app/process running; tab can be closed/reopened.
