# Autonomous Improvement Loop — Project Configuration

> Fill in this file after installing the skill to bind it to your project.

## Project
project_path: .
project_kind: generic   # software | writing | video | research | generic

## GitHub Repository
repo: https://github.com/OWNER/REPO

## OpenClaw Agent ID
agent_id: YOUR_AGENT_ID

## Telegram Chat ID
chat_id: YOUR_TELEGRAM_CHAT_ID

## Project Language
project_language:      # optional: "en" or "zh"; empty = follow agent preference, then project detection, then English

## Verification & Publish
verification_command:   # empty = no auto-verification
publish_command:        # optional: shell command after successful task

## Cron
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
cron_job_id:
