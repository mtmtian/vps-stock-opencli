# Project Instructions

- This repository contains only the read-only VPS inventory monitor; do not add proxy deployment, Mihomo/Clash generation, server profiles, or node credentials.
- Run from the repository root and keep the executable at `tools/vps_stock.py`.
- Never log in to provider accounts, add products to carts, order servers, change deployments, or touch remote hosts.
- Treat official public inventory pages as orderability signals, not guaranteed provisioning; label social and third-party catalog results as leads pending official verification.
- Keep runtime state outside Git under `~/.cache/vps-stock-opencli/`; never commit state snapshots, webhook URLs, cookies, tokens, or credentials.
- The executable may write only its explicit state artifacts and optional notification record; it must not write Codex/Claude automation memory or hidden host-specific project state.
- Optional discovery commands (`opencli` and `mcporter`) may be unavailable; report their failure without weakening official-source checks.
- Validate changes with `python3 -m py_compile tools/vps_stock.py` and `python3 -m unittest tests.test_vps_stock`.
