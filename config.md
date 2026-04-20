# Autonomous Improvement Loop — Project Configuration

> Fill in this file after installing the skill to bind it to your project.

## Project
project_path: /Users/weiminglu/Projects/autonomous-improvement-loop
project_kind: software   # software | writing | video | research | generic

## GitHub Repository
repo: https://github.com/WeimingLu1/autonomous-improvement-loop

## OpenClaw Agent ID
agent_id: mia

## Telegram Chat ID
chat_id:

## Project Language
project_language: zh

## Queue
min_queue_items: 6
heartbeat_path: /Users/weiminglu/.openclaw/workspace-mia/skills/autonomous-improvement-loop/HEARTBEAT.md

## Verification & Publish
verification_command:   # empty = no auto-verification
publish_command:        # optional: shell command after successful task

## Cron
cron_schedule: */30 * * * *
cron_timeout: 3600
cron_job_id: 9a18a926-e25d-4e91-a3b3-5b2b3d62aec0
