# Autonomous Improvement Loop — Project Configuration

> Fill in this file after installing the skill to bind it to your project.

## Project
project_path: /path/to/your/project
project_kind: software   # software | writing | video | research | generic

## GitHub Repository
repo: https://github.com/YOUR_USERNAME/YOUR_REPO

## OpenClaw Agent ID
agent_id: YOUR_AGENT_ID

## Telegram Chat ID
chat_id: YOUR_CHAT_ID

## Project Language
project_language: en   # "en" = English, "zh" = Chinese

## Queue
min_queue_items: 6
heartbeat_path:   # defaults to skill directory if empty

## Verification & Publish
verification_command:   # empty = no auto-verification
publish_command:        # optional: shell command after successful task

## Cron
cron_schedule: */30 * * * *
cron_timeout: 3600
cron_job_id:   # filled automatically by a-start
