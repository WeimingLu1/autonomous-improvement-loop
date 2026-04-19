import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))
from project_insights import refresh_queue, detect_project_type

project = Path('/Users/weiminglu/Projects/HealthAgent')
heartbeat = Path('/Users/weiminglu/.openclaw/workspace-viya/skills/autonomous-improvement-loop/HEARTBEAT.md')
lang = 'zh'
min_items = 5

ptype = detect_project_type(project)
print(f"[project_insights] type={ptype} lang={lang}")
added = refresh_queue(project, heartbeat, lang, min_items)
print(f"Done. Added {added} items.")