# Blockers and Open Questions

## Docker Desktop / Live FalkorDB Environment
- **Status**: Recorded for Phase A0.
- **Detail**: Docker Desktop daemon is not currently active on the host machine (`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`).
- **Mitigation / Next Step**: `docker-compose.yml` has been defined. Prototype query runner and tests support both live FalkorDB (when Docker container is started via `docker compose up -d`) and verified offline openCypher dialect emulation. To run against a live FalkorDB container, the user or host environment should launch Docker Desktop.

