# Reference: Testing Checklist

## Pre-flight Verification

Verify your skill installation is healthy before deploying to production.

### 1. Scripts compile cleanly

```bash
python3 -m py_compile ~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/scripts/*.py
```

Expected: no output = all syntax OK.

### 2. init.py works

```bash
# Show help
python3 scripts/init.py --help

# Show status (will show generic since project_kind not configured yet)
python3 scripts/init.py status .

# Show adopt help
python3 scripts/init.py adopt --help
```

### 3. project_insights.py works

```bash
# Scan once
python3 scripts/project_insights.py --project . --heartbeat HEARTBEAT.md --language en

# Refresh queue to 5 items
python3 scripts/project_insights.py --project . --heartbeat HEARTBEAT.md --language en --refresh --min 5
```

### 4. verify_and_revert.py works

```bash
python3 scripts/verify_and_revert.py --help
```

### 5. run_status.py works

```bash
python3 scripts/run_status.py --heartbeat HEARTBEAT.md read
```

## Adoption Testing

```bash
# Test adopt on a real project
python3 scripts/init.py adopt ~/Projects/YOUR_PROJECT

# Cron should be created
openclaw cron list

# Queue should have at least 5 items
cat HEARTBEAT.md
```

## Per-Project-Type Verification

### Software project

```bash
verification_command: pytest tests/ -q
```

### Writing project

```bash
verification_command: python -m spellcheck .
```

### Video project

```bash
verification_command: ffprobe -v error -show_entries format=duration -i footage.mov
```

### Generic project

```bash
verification_command:   # empty = manual verification
```

## Git / CI Integration

```bash
# Commit new changes
git add -A && git commit -m "chore: update skill"

# Push to GitHub
git push

# Publish to ClawHub
clawhub publish . --slug YOUR_SLUG --version X.Y.Z --changelog "..."
```
