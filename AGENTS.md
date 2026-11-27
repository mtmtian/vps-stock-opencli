# Project Instructions

- This repository contains only the read-only VPS inventory monitor; do not add proxy deployment, Mihomo/Clash generation, server profiles, or node credentials.
- Run from the repository root and keep the executable at `tools/vps_stock.py`.
- Default CLI mode monitors the dynamic ByteVirt Japan ISP and Los Angeles CN2 GIA families, ByteVirt PID 329 annual, PID 324 prepaid, and YINNET Singapore VPS ①. Keep old provider, social, and discovery checks out of default mode; `--legacy` and compatible historical selection flags are the only way to select them.
- Keep formal standalone sources under `tools/` with a `collect()` API. `tools/bytevirt_source.py` must reuse `tools/vps_stock.py`'s ByteVirt parser rather than implementing a second parser.
- Keep the default target-mode state separate from legacy `vps-stock.json`; explicit `--state-file` remains caller-owned. Do not add local scheduling, machine-specific absolute paths, notification credentials, or automation configuration to this public repository.
- Never log in to provider accounts, add products to carts, order servers, change deployments, or touch remote hosts.
- Treat official public inventory pages as orderability signals, not guaranteed provisioning; label social and third-party catalog results as leads pending official verification.
- Keep runtime state outside Git under `~/.cache/vps-stock-opencli/`; never commit state snapshots, webhook URLs, cookies, tokens, or credentials.
- The executable may write only its explicit state artifacts and optional notification record; it must not write Codex/Claude automation memory or hidden host-specific project state.
- Optional discovery commands (`opencli` and `mcporter`) may be unavailable; report their failure without weakening official-source checks.
- Validate changes with `python3 -m compileall -q tools` and `python3 -m unittest discover -s tests`.
