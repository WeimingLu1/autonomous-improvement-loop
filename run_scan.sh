#!/bin/bash
cd /Users/weiminglu/.openclaw/workspace-viya/skills/autonomous-improvement-loop
export PYTHONPATH="$PWD:$PYTHONPATH"
python3 - <<'EOF'
import sys
sys.path.insert(0, 'scripts')
from project_insights import main
sys.argv = [
    'project_insights.py',
    '--project', '/Users/weiminglu/Projects/HealthAgent',
    '--heartbeat', 'HEARTBEAT.md',
    '--language', 'zh',
    '--refresh',
    '--min', '5'
]
raise SystemExit(main())
EOF