# Pre-Flight Checklist

Run this before the first cron trigger to ensure everything works.

## Environment

```bash
# 1. gh authenticated
gh auth status
# Expected: √ Logged in to github.com as YOU

# 2. Project exists and accessible
ls ~/Projects/PROJECT
# Expected: project directory exists

# 3. VERSION file exists
cat ~/Projects/PROJECT/VERSION
# Expected: e.g. "0.0.1"

# 4. docs/agent/ exists
ls ~/Projects/PROJECT/docs/agent/
# Expected: directory exists (even if empty)

# 5. Python venv exists
ls ~/Projects/PROJECT/.venv/bin/activate
# Expected: activate script exists

# 6. pytest works
cd ~/Projects/PROJECT && source .venv/bin/activate && pytest -q
# Expected: N passed (no failures)
```

## Skill Scripts

```bash
# 7. Automation scripts exist and are executable
ls ~/.openclaw/workspace-viya/skills/autonomous-improvement-loop/scripts/
# Expected: run_status.py queue_scanner.py verify_cli_docs.py rollback_if_unstable.py

# 8. Scripts have no syntax errors
python3 -m py_compile ~/.openclaw/workspace-viya/skills/autonomous-improvement-loop/scripts/*.py
# Expected: no output

# 9. run_status.py works
python3 scripts/run_status.py --heartbeat ~/.openclaw/workspace-viya/HEARTBEAT.md read
# Expected: last_run_time=never last_run_commit=none last_run_result=unknown

# 10. queue_scanner.py --help works
python3 scripts/queue_scanner.py --help
# Expected: usage with --project and --heartbeat
```

## Cron Job

```bash
# 11. Cron job created
openclaw cron list
# Expected: shows your job with correct ID

# 12. Cron job description correct
# Check: ID, session=isolated, model=YOUR_MODEL, every=30m

# 13. delivery configured (announce → Telegram)
# Should see: mode=announce, channel=telegram, to=YOUR_CHAT_ID

# 14. timeout set to 3600 (1 hour)
# Should see: timeoutSeconds: 3600
```

## Workspace Files

```bash
# 15. HEARTBEAT.md exists with Run Status block
ls ~/.openclaw/workspace-viya/HEARTBEAT.md
# Check: contains "## Run Status" near the top

# 16. DEVLOG.md exists
ls ~/.openclaw/workspace-viya/DEVLOG.md

# 17. REPORT.md exists
ls ~/.openclaw/workspace-viya/REPORT.md

# 18. memory/ directory exists
ls ~/.openclaw/workspace-viya/memory/
```

## Telegram

```bash
# 19. Can send test message
# Try sending a test message to confirm Telegram works:
# openclaw send --channel telegram --to YOUR_CHAT_ID --message "Test from improvement loop"
```

## Post-Setup Verification

After first cron run completes, verify:

- [ ] GitHub has new commit(s)
- [ ] GitHub has new tag
- [ ] GitHub Release created
- [ ] VERSION file incremented
- [ ] Telegram received final report (one message per run, not per-step)
- [ ] docs/agent/ synced and pushed
- [ ] HEARTBEAT.md updated (task moved from QUEUED to archived)
- [ ] DEVLOG.md updated (completed item added)
- [ ] Run Status block updated with pass/fail and commit hash
- [ ] Queue has new items if queue_scanner found opportunities

## Common Issues

| Symptom | Fix |
|---------|-----|
| `gh release` fails | Run `gh auth login` |
| pytest import errors | Activate venv: `source .venv/bin/activate` |
| Telegram no messages | Check chat_id is correct E.164 format |
| Cron not triggering | Check `openclaw cron list` shows `idle` or `ok`, not `disabled` |
| delivery empty | Need `--announce --channel telegram --to CHAT_ID` when creating |
| Job times out | Increase `--timeout-seconds` to 3600 |
| Agent tries to do everything in one run | Ensure cron message includes "每次运行只完成一件事，然后停止" |
| rollback_if_unstable fails | Check run_status.py path is correct and writable |
