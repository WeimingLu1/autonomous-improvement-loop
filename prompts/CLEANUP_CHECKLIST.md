# Cleanup Checklist

> Post-run verification checklist for the Autonomous Improvement Loop skill.

## After Each Task

- [ ] Task was implemented correctly
- [ ] `git commit` was created with a clear message
- [ ] HEARTBEAT.md Run Status updated (last_run_time, last_run_commit, last_run_result, last_run_task)
- [ ] Queue entry marked `done` (or `skip` if intentionally skipped)
- [ ] Telegram report sent (if chat_id is configured)

## Verification Command

- [ ] `verification_command` from config.md was run (if configured)
- [ ] On failure: commit was reverted and pushed
- [ ] On success: changes were pushed to remote

## Queue Maintenance

- [ ] Queue has at least 5 pending items (run `project_insights.py --refresh --min 5` if needed)
- [ ] No duplicate entries in queue
- [ ] `done` entries are not re-sorted back into pending

## Cron Safety

- [ ] `cron_lock` is `false` after run completes
- [ ] No concurrent runs overlap (cron_lock prevents this)
- [ ] Cron schedule is correct (`*/30 * * * *` or as configured)

## General

- [ ] No hardcoded personal paths or credentials in skill files
- [ ] All new scripts pass `python3 -m py_compile`
- [ ] README.md / SKILL.md reflect current architecture
