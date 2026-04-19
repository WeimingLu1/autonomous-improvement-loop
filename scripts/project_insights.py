#!/usr/bin/env python3
"""Scan any project and append improvement candidates to HEARTBEAT.md.

This is the core "eyes" of the improvement loop. It auto-detects the project
type and generates relevant, actionable improvement ideas \u2014 regardless of whether
the project is software, a novel, a video script, or a research paper.

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
PROJECT TYPES & THEIR BUCKETS
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

software  \u2192 test, doc, todo, ux, feature, data, engage, inspire
writing    \u2192 plot, character, pace, dialogue, structure, clarity, inspire
video      \u2192 script, pacing, visual, continuity, audio, edit, inspire
research   \u2192 structure, citation, clarity, method, conclusion, inspire
generic    \u2192 structure, clarity, consistency, completeness, inspire

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
USAGE
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

# Scan once and append ONE best candidate
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en

# Keep scanning until queue has at least N items
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en --refresh --min 5
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# \u2500\u2500 Project type detection \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def detect_project_type(project: Path) -> str:
    """Return: software | writing | video | research | generic"""
    all_files = [f.name.lower() for f in project.rglob("*") if f.is_file()]
    all_dirs = {d.name.lower() for d in project.rglob("*") if d.is_dir()}

    software_indicators = {
        "src", "lib", "app", "packages",
        "tests", "test", "__pycache__",
        "package.json", "cargo.toml", "go.mod", "go.sum",
        "pyproject.toml", "setup.py", "requirements.txt",
        "pom.xml", "build.gradle", "Gemfile",
    }
    software_score = sum(1 for i in software_indicators if i in all_files or i in all_dirs)
    if software_score >= 2:
        return "software"

    writing_indicators = {
        "chapters", "chapter", "scenes", "scene",
        "manuscript", "characters", "outline", "drafts",
    }
    md_count = sum(1 for f in all_files if f.endswith(".md") and "readme" not in f)
    writing_score = sum(1 for i in writing_indicators if i in all_dirs) + (1 if md_count >= 5 else 0)
    if writing_score >= 2 or md_count >= 10:
        return "writing"

    video_indicators = {
        "scripts", "scenes", "storyboard", "footage",
        "shots", "sequences", "edit", "cuts", "assets",
    }
    video_score = sum(1 for i in video_indicators if i in all_dirs)
    if video_score >= 2:
        return "video"

    research_indicators = {
        "papers", "references", "bib", "tex",
        "citations", "notes", "journal", "figures",
    }
    research_score = sum(1 for i in research_indicators if i in all_dirs)
    if research_score >= 1 and any(f.endswith(".tex") or "bib" in f for f in all_files):
        return "research"

    return "generic"


# \u2500\u2500 Buckets per project type \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def _software_buckets(lang: str):
    en = lang == "en"
    return [
        ("inspire", [
            "哪些开发者体验痛点还没被解决？" if not en else "哪些 developer-experience pain points remain unsolved?",
            "CLI 工具有哪些交互范式可以创新？" if not en else "What CLI interaction paradigms could be reimagined?",
            "竞品的哪些亮点功能我们可以借鉴但还未实现？" if not en else "What competitor亮点 features could we adopt but haven't?",
            "错误信息能否更人性化，给出修复建议而非仅报错误？" if not en else "Can error messages be more human: suggest fixes, not just errors?",
        ]),
        ("test", [
            "Add unit tests for each untested module" if en else "\u4e3a\u6bcf\u4e2a\u672a\u6d4b\u8bd5\u7684\u6a21\u5757\u8865\u9f50\u5355\u5143\u6d4b\u8bd5",
            "Increase test coverage for edge cases" if en else "\u4e3a\u8fb9\u754c\u60c5\u51b5\u589e\u52a0\u6d4b\u8bd5\u8986\u76d6",
            "Add integration tests for critical user flows" if en else "\u4e3a\u5173\u952e\u7528\u6237\u6d41\u7a0b\u589e\u52a0\u96c6\u6210\u6d4b\u8bd5",
            "Ensure all error paths have corresponding tests" if en else "\u786e\u4fdd\u6240\u6709\u9519\u8bef\u8def\u5f84\u90fd\u6709\u5bf9\u5e94\u6d4b\u8bd5",
        ]),
        ("doc", [
            "Add module-level docstrings to undocumented modules" if en else "\u4e3a\u672a\u5199\u6587\u6863\u7684\u6a21\u5757\u8865\u5145 docstring",
            "Document public API contracts with usage examples" if en else "\u4e3a\u516c\u5f00 API \u5199\u6e05\u5408\u7ea6\u548c\u4f7f\u7528\u793a\u4f8b",
            "Add inline comments explaining non-obvious logic" if en else "\u4e3a\u4e0d\u76f4\u89c2\u903b\u8f91\u589e\u52a0\u6ce8\u91ca\u8bf4\u660e",
        ]),
        ("todo", [
            "Address all TODO/FIXME comments in the codebase" if en else "\u5904\u7406\u4ee3\u7801\u5e93\u4e2d\u7684\u6240\u6709 TODO/FIXME",
            "Audit deprecated code paths and remove or document them" if en else "\u5ba1\u67e5\u5e76\u79fb\u9664\u6216\u6807\u6ce8\u5e9f\u5f03\u4ee3\u7801\u8def\u5f84",
        ]),
        ("ux", [
            "Improve error messages: show the cause and a suggested fix" if en else "\u6539\u8fdb\u9519\u8bef\u63d0\u793a\uff1a\u7ed9\u51fa\u539f\u56e0\u548c\u4fee\u590d\u5efa\u8bae",
            "Add a verbose mode (--verbose) for detailed execution info" if en else "\u589e\u52a0 verbose \u6a21\u5f0f\uff08--verbose\uff09\u8f93\u51fa\u8be6\u7ec6\u4fe1\u606f",
            "Add shell completions (bash/zsh/fish) for the CLI" if en else "\u4e3a CLI \u589e\u52a0 shell \u81ea\u52a8\u8865\u5168\uff08bash/zsh/fish\uff09",
            "Add a config file (~/.myapp.yaml) for user preferences" if en else "\u589e\u52a0\u914d\u7f6e\u6587\u4ef6\uff08~/.myapp.yaml\uff09\u652f\u6301\u7528\u6237\u504f\u597d\u8bbe\u7f6e",
        ]),
        ("feature", [
            "Identify the most requested unimplemented feature and add it" if en else "\u627e\u51fa\u6700\u88ab\u671f\u5f85\u4f46\u672a\u5b9e\u73b0\u7684\u529f\u80fd\u5e76\u5b9e\u73b0",
            "Add a status command showing current project state at a glance" if en else "\u589e\u52a0 status \u547d\u4ee4\uff1a\u4e00\u89c8\u5f53\u524d\u9879\u76ee\u72b6\u6001",
        ]),
        ("data", [
            "Add an export command for structured data output" if en else "\u589e\u52a0 export \u547d\u4ee4\u8f93\u51fa\u7ed3\u6784\u5316\u6570\u636e",
            "Add a backup/restore mechanism for project data" if en else "\u589e\u52a0\u9879\u76ee\u6570\u636e\u7684\u5907\u4efd/\u6062\u590d\u673a\u5236",
        ]),
        ("engage", [
            "Add an achievement or milestone system to reward consistency" if en else "\u589e\u52a0\u6210\u5c31/\u91cc\u7a0b\u7891\u7cfb\u7edf\uff0c\u5956\u52b1\u6301\u7eed\u6295\u5165",
            "Add a streak tracker for consecutive days of work" if en else "\u589e\u52a0\u8fde\u7eed\u8bb0\u5f55\u8ffd\u8e2a\uff0c\u6fc0\u52b1\u4fdd\u6301\u8282\u594f",
        ]),
    ]


def _writing_buckets(lang: str):
    en = lang == "en"
    return [
        ("inspire", [
            "情节张力是否足够？读者在哪个节点可能弃书？" if not en else "Is the plot tension sufficient? Where might readers abandon the book?",
            "角色动机是否清晰？每个决定是否有足够铺垫？" if not en else "Are character motivations clear? Does each decision have enough setup?",
            "开头能否更抓人？是否能在前 500 字内建立强烈期待感？" if not en else "Can the opening be more gripping? Does it build strong anticipation in the first 500 words?",
            "读者评论/反馈中最高频的问题是什么？" if not en else "What are the most frequently mentioned reader complaints or questions?",
        ]),
        ("plot", [
            "Review plot consistency: check for timeline contradictions" if en else "\u5ba1\u67e5\u60c5\u8282\u4e00\u81f4\u6027\uff1a\u68c0\u67e5\u65f6\u95f4\u7ebf\u77db\u76fe",
            "Identify and resolve any unresolved plot threads from earlier chapters" if en else "\u627e\u51fa\u5e76\u89e3\u51b3\u65e9\u671f\u7ae0\u8282\u9057\u7559\u7684\u672a\u89e3\u60c5\u8282\u7ebf\u7d22",
            "Strengthen the central conflict: does it sustain through the middle?" if en else "\u5f3a\u5316\u6838\u5fc3\u51b2\u7a81\uff1a\u662f\u5426\u80fd\u6491\u8fc7\u4e2d\u6bb5\uff1f",
            "Review chapter hooks: does each chapter end with tension?" if en else "\u5ba1\u67e5\u7ae0\u8282\u94a9\u5b50\uff1a\u6bcf\u4e2a\u7ae0\u8282\u7ed3\u5c3e\u662f\u5426\u6709\u60ac\u5ff5\uff1f",
        ]),
        ("character", [
            "Review character voice consistency: does each character sound distinct?" if en else "\u5ba1\u67e5\u89d2\u8272\u58f0\u97f3\u4e00\u81f4\u6027\uff1a\u6bcf\u4e2a\u89d2\u8272\u662f\u5426\u6709\u72ec\u7279\u8bed\u8a00\u98ce\u683c\uff1f",
            "Audit character motivations: does each major choice stem from established desire/fear?" if en else "\u5ba1\u67e5\u89d2\u8272\u52a8\u673a\uff1a\u6bcf\u4e2a\u91cd\u5927\u9009\u62e9\u662f\u5426\u6e90\u4e8e\u5df2\u6709\u6b32\u671b\u6216\u6050\u60e7\uff1f",
            "Review secondary character arcs: do they change by the end?" if en else "\u5ba1\u67e5\u6b21\u8981\u89d2\u8272\u5f27\u7ebf\uff1a\u4ed6\u4eec\u6700\u7ec8\u6709\u6539\u53d8\u5417\uff1f",
        ]),
        ("pace", [
            "Identify the slowest 20% of scenes: can they be cut or tightened?" if en else "\u627e\u51fa\u6700\u62d6\u6c93\u7684 20% \u573a\u666f\uff1a\u80fd\u5426\u7cbe\u7b80\uff1f",
            "Review the 'sagging middle': is the middle third compelling?" if en else "\u5ba1\u67e5'\u584c\u9677\u4e2d\u90e8'\uff1a\u4e2d\u6bb5\u4e09\u5206\u4e4b\u4e00\u662f\u5426\u5438\u5f15\uff1f",
            "Check that the opening chapter hooks immediately" if en else "\u68c0\u67e5\u5f00\u5934\u7ae0\u8282\u662f\u5426\u7acb\u523b\u6293\u4f4f\u8bfb\u8005",
        ]),
        ("dialogue", [
            "Read each chapter's dialogue aloud: does it sound natural?" if en else "\u6717\u8bfb\u6bcf\u7ae0\u5bf9\u8bdd\uff1a\u542c\u8d77\u6765\u81ea\u7136\u5417\uff1f",
            "Replace generic dialogue with character-specific voice" if en else "\u7528\u89d2\u8272\u7279\u6709\u7684\u58f0\u97f3\u66ff\u6362\u901a\u7528\u5bf9\u8bdd",
        ]),
        ("structure", [
            "Check that each scene has a clear objective, conflict, and outcome" if en else "\u68c0\u67e5\u6bcf\u4e2a\u573a\u666f\u662f\u5426\u6709\u6e05\u6670\u7684\u76ee\u6807\u3001\u51b2\u7a81\u548c\u7ed3\u679c",
            "Identify scenes that could be combined or cut entirely" if en else "\u627e\u51fa\u53ef\u4ee5\u5408\u5e76\u6216\u5b8c\u5168\u5220\u9664\u7684\u573a\u666f",
        ]),
        ("clarity", [
            "Replace telling with showing: find instances of summary rather than scene" if en else "\u628a\u53d9\u8ff0\u6362\u6210\u5c55\u793a\uff1a\u627e\u51fa\u6982\u62ec\u800c\u975e\u573a\u666f\u5316\u7684\u6bb5\u843d",
            "Check that each paragraph has a clear controlling idea" if en else "\u68c0\u67e5\u6bcf\u4e2a\u6bb5\u843d\u662f\u5426\u6709\u6e05\u6670\u7684\u4e2d\u5fc3\u601d\u60f3",
        ]),
    ]


def _video_buckets(lang: str):
    en = lang == "en"
    return [
        ("inspire", [
            "开头 3 秒能否抓住观众？" if not en else "Can the opening 3 seconds capture the audience?",
            "节奏是否拖沓？每个镜头是否有存在的理由？" if not en else "Is the pacing sluggish? Does every shot have a reason to exist?",
            "视觉和声音的配合是否到位？是否有无声浪费？" if not en else "Does visual-audio sync work well? Any silent dead weight?",
            "情绪曲线是否完整？起承转合是否平滑？" if not en else "Is the emotional arc complete? Does the structure flow smoothly?",
        ]),
        ("script", [
            "Review scene objectives: does each scene have a clear purpose?" if en else "\u5ba1\u67e5\u573a\u666f\u76ee\u6807\uff1a\u6bcf\u4e2a\u573a\u666f\u662f\u5426\u6709\u6e05\u6670\u76ee\u7684\uff1f",
            "Review the cold open: does it hook in the first 30 seconds?" if en else "\u5ba1\u67e5\u5f00\u5934\uff1a\u524d 30 \u79d2\u662f\u5426\u6293\u4f4f\u89c2\u4f17\uff1f",
            "Add camera direction notes to action scenes" if en else "\u4e3a\u52a8\u4f5c\u573a\u666f\u589e\u52a0\u6444\u5f71\u6307\u5bfc\u5907\u6ce8",
        ]),
        ("pacing", [
            "Map the emotional arc beat-by-beat: is there enough variation?" if en else "\u9010 Beat \u5730\u56fe\u60c5\u611f\u5f27\u7ebf\uff1a\u53d8\u5316\u591f\u5417\uff1f",
            "Review the runtime: does it match the intended format/length?" if en else "\u5ba1\u67e5\u65f6\u957f\uff1a\u662f\u5426\u7b26\u5408\u76ee\u6807\u683c\u5f0f/\u957f\u5ea6\uff1f",
        ]),
        ("visual", [
            "Review shot list for visual variety: avoid repetitive shot types" if en else "\u5ba1\u67e5\u955c\u5934\u8868\uff1a\u907f\u514d\u91cd\u590d\u7684\u955c\u5934\u7c7b\u578b",
            "Check that key visual moments are staged for maximum impact" if en else "\u68c0\u67e5\u5173\u952e\u89c6\u89c9\u65f6\u523b\u662f\u5426\u88ab\u8bbe\u8ba1\u5f97\u6700\u5177\u51b2\u51fb\u529b",
        ]),
        ("continuity", [
            "Create a continuity log for props, costumes, and set elements" if en else "\u4e3a\u9053\u5177\u3001\u670d\u88c5\u548c\u5e03\u666f\u5143\u7d20\u5efa\u7acb\u8fde\u7eed\u6027\u65e5\u5fd7",
            "Review timeline consistency: do time-of-day cues stay coherent?" if en else "\u5ba1\u67e5\u65f6\u95f4\u7ebf\u4e00\u81f4\u6027\uff1a\u65e5\u591c\u7ebf\u7d22\u662f\u5426\u8fde\u8d2f\uff1f",
        ]),
        ("audio", [
            "Review audio cue placement: do sound effects support the visuals?" if en else "\u5ba1\u67e5\u97f3\u6548cue\u4f4d\u7f6e\uff1a\u97f3\u6548\u662f\u5426\u914d\u5408\u753b\u9762\uff1f",
            "Check that music choices reinforce the emotional tone" if en else "\u68c0\u67e5\u97f3\u4e50\u9009\u62e9\u662f\u5426\u5f3a\u5316\u60c5\u611f\u57fa\u8c03",
        ]),
        ("edit", [
            "Review cuts: do they feel motivated or arbitrary?" if en else "\u5ba1\u67e5\u5207\u6362\uff1a\u662f\u6709\u52a8\u673a\u8fd8\u662f\u968f\u610f\uff1f",
            "Review the final 30 seconds: does it end with impact?" if en else "\u5ba1\u67e5\u6700\u540e 30 \u79d2\uff1a\u662f\u5426\u6709\u51b2\u51fb\u529b\u7ed3\u5c3e\uff1f",
        ]),
    ]


def _research_buckets(lang: str):
    en = lang == "en"
    return [
        ("inspire", [
            "研究问题是否足够聚焦而非泛泛而谈？" if not en else "Is the research question sufficiently focused rather than vague?",
            "方法论是否足够透明可复现？" if not en else "Is the methodology transparent and reproducible?",
            "与最新文献相比，这个研究的增量贡献是什么？" if not en else "What is this study's incremental contribution vs. the latest literature?",
            "结论是否被数据充分支持而非过度推论？" if not en else "Are conclusions fully supported by data, not over-interpreted?",
        ]),
        ("structure", [
            "Verify the paper structure: abstract \u2192 intro \u2192 method \u2192 results \u2192 discussion" if en else "\u6838\u67e5\u8bba\u6587\u7ed3\u6784\uff1a\u6458\u8981\u2192\u5f15\u8a00\u2192\u65b9\u6cd5\u2192\u7ed3\u679c\u2192\u8ba8\u8bba",
            "Ensure the abstract is self-contained and summaries all sections" if en else "\u786e\u4fdd\u6458\u8981\u72ec\u7acb\u5b8c\u6574\uff0c\u6982\u62ec\u6240\u6709\u90e8\u5206",
        ]),
        ("citation", [
            "Add missing citations: check for uncited references and unlisted sources" if en else "\u8865\u5145\u9057\u6f0f\u5f15\u7528\uff1a\u68c0\u67e5\u672a\u5f15\u7528\u7684\u53c2\u8003\u6587\u732e\u548c\u672a\u5217\u51fa\u6765\u6e90",
            "Ensure citations are up-to-date: add recent related work" if en else "\u786e\u4fdd\u5f15\u7528\u6700\u65b0\uff1a\u8865\u5145\u8fd1\u5e74\u76f8\u5173\u5de5\u4f5c",
            "Check that all figures and tables are cited in the text" if en else "\u68c0\u67e5\u6240\u6709\u56fe\u8868\u662f\u5426\u5728\u6b63\u6587\u4e2d\u88ab\u5f15\u7528",
        ]),
        ("clarity", [
            "Replace jargon with accessible language where possible" if en else "\u5728\u53ef\u80fd\u7684\u5730\u65b9\u7528\u901a\u4fd7\u8bed\u8a00\u66ff\u6362\u672f\u8bed",
            "Check that all abbreviations are defined on first use" if en else "\u68c0\u67e5\u6240\u6709\u7f29\u5199\u662f\u5426\u5728\u9996\u6b21\u4f7f\u7528\u65f6\u5b9a\u4e49",
        ]),
        ("method", [
            "Verify methodology is described in enough detail to reproduce" if en else "\u6838\u5b9e\u65b9\u6cd5\u8bba\u63cf\u8ff0\u8db3\u591f\u8be6\u7ec6\uff0c\u53ef\u590d\u73b0",
            "Check that limitations are acknowledged transparently" if en else "\u68c0\u67e5\u5c40\u9650\u6027\u662f\u5426\u88ab\u900f\u660e\u627f\u8ba4",
        ]),
        ("conclusion", [
            "Verify that conclusions are supported by the data presented" if en else "\u6838\u5b9e\u7ed3\u8bba\u7531\u6240\u5448\u6570\u636e\u652f\u6491",
            "Check that implications are discussed without overgeneralizing" if en else "\u68c0\u67e5\u662f\u5426\u8ba8\u8bba\u610f\u4e49\u800c\u4e0d\u8fc7\u5ea6\u6cdb\u5316",
        ]),
    ]


def _generic_buckets(lang: str):
    en = lang == "en"
    return [
        ("inspire", [
            "工作流程中最费力的环节是什么？" if not en else "What is the most laborious part of the workflow?",
            "哪些重复劳动可以消除或自动化？" if not en else "What repetitive work can be eliminated or automated?",
            "信息传递中哪些地方最容易出错或被误解？" if not en else "Where is information transfer most likely to break down or be misunderstood?",
        ]),
        ("structure", [
            "Review overall project structure: is the hierarchy logical and navigable?" if en else "\u5ba1\u67e5\u6574\u4f53\u9879\u76ee\u7ed3\u6784\uff1a\u5c42\u6b21\u662f\u5426\u903b\u8f91\u6e05\u6670\uff1f",
            "Identify any orphaned or unlinked content that should be integrated" if en else "\u627e\u51fa\u5b64\u7acb\u6216\u672a\u94fe\u63a5\u7684\u5185\u5bb9\uff0c\u5e94\u6574\u5408",
        ]),
        ("clarity", [
            "Audit terminology consistency across all documents" if en else "\u5ba1\u67e5\u6240\u6709\u6587\u6863\u7684\u672f\u8bed\u4e00\u81f4\u6027",
            "Review any ambiguous or vague statements and make them precise" if en else "\u5ba1\u67e5\u6a21\u7cca\u9648\u8ff0\uff0c\u4f7f\u5176\u7cbe\u786e",
        ]),
        ("consistency", [
            "Check naming conventions: are they applied uniformly?" if en else "\u68c0\u67e5\u547d\u540d\u89c4\u8303\uff1a\u662f\u5426\u7edf\u4e00\u5e94\u7528\uff1f",
            "Review tone and voice: is it consistent throughout?" if en else "\u5ba1\u67e5\u8bed\u6c14\u548c\u98ce\u683c\uff1a\u5168\u6587\u4e00\u81f4\u5417\uff1f",
        ]),
        ("completeness", [
            "Identify sections that end abruptly and need development" if en else "\u627e\u51fa\u621b\u7136\u800c\u6b62\u7684\u7ae0\u8282\uff0c\u9700\u8981\u5145\u5b9e",
            "Review the outline: are there gaps in coverage?" if en else "\u5ba1\u67e5\u5927\u7eb2\uff1a\u8986\u76d6\u662f\u5426\u6709\u7a7a\u767d\uff1f",
        ]),
        ("workflow", [
            "Identify manual steps that could be automated or templated" if en else "\u627e\u51fa\u53ef\u4ee5\u81ea\u52a8\u5316\u6216\u6a21\u677f\u5316\u7684\u624b\u52a8\u6b65\u9aa4",
            "Check that key decisions and their rationale are documented" if en else "\u68c0\u67e5\u5173\u952e\u51b3\u7b56\u548c\u7406\u7531\u662f\u5426\u88ab\u8bb0\u5f55",
        ]),
    ]


def get_buckets(project_type: str, lang: str):
    return {
        "software": _software_buckets,
        "writing": _writing_buckets,
        "video": _video_buckets,
        "research": _research_buckets,
        "generic": _generic_buckets,
    }[project_type](lang)


# \u2500\u2500 Core queue logic \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


def _strip_prefix(content: str) -> str:
    content = re.sub(r'^\[\[[^\]]+\]\]\s*score=\d+\s*\|\s*', '', content).strip()
    content = re.sub(r'^\[\[[^\]]+\]\]\s*', '', content).strip()
    return content


def _table_cell(line: str, col: int) -> str:
    cells = [c.strip() for c in line.split('|')]
    return cells[col + 1] if col + 1 < len(cells) else ''


def existing_queue_normalized(heartbeat: Path) -> set[str]:
    """Normalized content strings already in the queue."""
    content = heartbeat.read_text(encoding="utf-8")
    seen: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or stripped.startswith('|---'):
            continue
        if not re.match(r'^\|\s*(\d+)\s*\|', stripped):
            continue
        cell4 = _table_cell(stripped, 3)
        seen.add(_normalize(_strip_prefix(cell4)).lower())
    return seen


def _get_inspire_questions(ptype: str, lang: str) -> list[str]:
    """Extract inspire questions for the given project type (2-3 questions)."""
    buckets = get_buckets(ptype, lang)
    for bucket_name, ideas in buckets:
        if bucket_name == "inspire":
            # Return 2-3 questions, alternating for variety
            return ideas[:3]
    return []


def call_llm(finding: str, bucket_name: str, inspire_context: list[str], lang: str) -> tuple[str, str]:
    """Stub for LLM-powered creative improvement suggestion.

    In production, this would call an LLM API with the finding and inspire
    questions as context, returning (improved_finding, detail).
    Returns the original finding with a concise detail that includes
    the inspire question that guided this selection.
    """
    if inspire_context:
        detail = f"{inspire_context[0]} | Bucket: {bucket_name}"
    else:
        detail = f"Bucket: {bucket_name}"
    return finding, detail


def choose_best_candidate(project: Path, heartbeat: Path, lang: str) -> tuple[str, str] | None:
    """Return the highest-priority new idea from all buckets.

    Returns (finding, detail) tuple where detail is the full analysis
    context (used as the Detail field when Source=agent).

    Note: items from the 'inspire' bucket are used as creative-context
    questions and are NOT returned as queue items directly. Instead,
    they populate the detail field of other bucket items.
    """
    ptype = detect_project_type(project)
    existing = existing_queue_normalized(heartbeat)

    # Extract inspire questions for type-aware creative context
    inspire_questions = _get_inspire_questions(ptype, lang)

    for bucket_name, ideas in get_buckets(ptype, lang):
        if bucket_name == "inspire":
            # Inspire bucket items are questions, not queue items — skip
            continue
        for idea in ideas:
            if _normalize(idea).lower() not in existing:
                # Use inspire context as detail for this finding
                finding, detail = call_llm(idea, bucket_name, inspire_questions, lang)
                return finding, detail
    return None


def score_finding(finding: str) -> int:
    fl = finding.lower()
    if any(k in fl for k in ['\u5355\u5143\u6d4b\u8bd5', '\u8865\u9f50', 'missing', 'undocumented']):
        return 50
    if any(k in fl for k in ['docstring', 'document', '\u6587\u6863', 'comment']):
        return 45
    if any(k in fl for k in ['plot', 'character', 'pacing', 'pace', '\u60c5\u8282', '\u89d2\u8272', '\u8282\u594f', 'voice']):
        return 65
    if any(k in fl for k in ['script', 'scene', 'shot', 'transition', '\u955c\u5934', '\u573a\u666f', '\u811a\u672c']):
        return 65
    if any(k in fl for k in ['citation', 'cite', 'reference', '\u5f15\u7528', '\u6587\u732e']):
        return 65
    if any(k in fl for k in ['insight', '\u667a\u80fd', 'predict', 'detect', '\u68c0\u6d4b']):
        return 72
    if any(k in fl for k in ['export', 'import', 'backup', '\u5bfc\u5165', '\u5bfc\u51fa']):
        return 65
    if any(k in fl for k in ['achievement', 'streak', '\u6210\u5c31', '\u8fde\u7eed', 'milestone']):
        return 68
    if any(k in fl for k in ['suggest', 'compare', 'undo', 'wizard', '\u5efa\u8bae', '\u64a4\u9500', '\u5bf9\u6bd4']):
        return 70
    if any(k in fl for k in ['error', 'verbose', 'config', 'confirm', '\u9519\u8bef', '\u8be6\u7ec6']):
        return 55
    if any(k in fl for k in ['structure', 'consistency', 'completeness', '\u7ed3\u6784', '\u4e00\u81f4', '\u5b8c\u6574']):
        return 60
    return 60


def append_to_queue(heartbeat: Path, finding: str, detail: str | None = None) -> bool:
    """Append a finding to the queue. detail defaults to finding if not provided."""
    content = heartbeat.read_text(encoding="utf-8")
    section_match = re.search(r'(## Queue\n\n)([\s\S]*?)(\n---\n)', content)
    if not section_match:
        print("ERROR: Queue section not found in HEARTBEAT.md", file=sys.stderr)
        return False

    score = score_finding(finding)
    section_body = section_match.group(2)
    numbers = [int(m) for m in re.findall(r'^\|\s*(\d+)\s*\|', section_body, re.MULTILINE)]
    next_num = max(numbers) + 1 if numbers else 1
    created = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    detail_str = finding if detail is None else detail

    new_line = f"| {next_num} | improve | {score} | [[Improve]] {finding} | {detail_str} | scanner | pending | {created} |"
    new_section = (
        section_match.group(1)
        + section_body.rstrip()
        + "\n"
        + new_line
        + "\n"
        + section_match.group(3)
    )
    updated = (
        content[:section_match.start()]
        + new_section
        + content[section_match.end():]
    )
    heartbeat.write_text(updated, encoding="utf-8")
    print(f"project_insights: +1 -> {new_line}")
    return True


def queue_count(heartbeat: Path) -> int:
    content = heartbeat.read_text(encoding="utf-8")
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or stripped.startswith('|---'):
            continue
        if not re.match(r'^\|\s*(\d+)\s*\|', stripped):
            continue
        cells = [c.strip() for c in stripped.split('|')]
        # Detail column added at index 5 (after Content at index 4)
        # Source is at index 5 (new) or old index 4
        status_idx = 7 if len(cells) >= 8 else 6
        if len(cells) >= 7 and 'pending' in cells[status_idx].lower():
            count += 1
    return count


def clear_queue(heartbeat: Path) -> int:
    """Remove all non-user entries from the queue. Returns count of removed entries."""
    content = heartbeat.read_text(encoding="utf-8")
    section_match = re.search(r'(## Queue\n\n)([\s\S]*?)(\n---\n)', content)
    if not section_match:
        print("ERROR: Queue section not found in HEARTBEAT.md", file=sys.stderr)
        return 0

    section_body = section_match.group(2)
    lines = section_body.rstrip('\n').split('\n')
    kept_lines: list[str] = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|') or stripped.startswith('|---'):
            continue
        if not re.match(r'^\|\s*(\d+)\s*\|', stripped):
            continue
        cells = [c.strip() for c in stripped.split('|')]
        # Source column: index 5 (new format with Detail) or index 4 (old format)
        source = cells[5] if len(cells) >= 6 else cells[4] if len(cells) >= 5 else ''
        if source == 'user':
            kept_lines.append(line)
        else:
            removed += 1

    new_section = (
        section_match.group(1)
        + ('\n'.join(kept_lines) + '\n' if kept_lines else '')
        + section_match.group(3)
    )
    updated = (
        content[:section_match.start()]
        + new_section
        + content[section_match.end():]
    )
    heartbeat.write_text(updated, encoding="utf-8")
    return removed


def refresh_queue(project: Path, heartbeat: Path, lang: str, min_items: int, detail: str | None = None) -> int:
    added = 0
    max_add = max(min_items * 3, 20)
    while queue_count(heartbeat) < min_items and added < max_add:
        result = choose_best_candidate(project, heartbeat, lang)
        if not result:
            print(f"project_insights: no more candidates, queue has {queue_count(heartbeat)} pending")
            break
        finding, _detail = result
        # CLI --detail overrides the LLM-generated detail
        final_detail = detail if detail is not None else _detail
        if append_to_queue(heartbeat, finding, final_detail):
            added += 1
    if added >= max_add and queue_count(heartbeat) < min_items:
        print(f"project_insights: safety stop after {added} additions; pending={queue_count(heartbeat)}")
    if added:
        print(f"project_insights: added {added} items (total pending: {queue_count(heartbeat)})")
    return added


# \u2500\u2500 CLI \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover improvement opportunities for any project type. "
        "Auto-detects: software, writing, video, research, generic."
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--heartbeat", required=True, type=Path)
    parser.add_argument("--language", default="en", choices=["en", "zh"])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min", type=int, default=5)
    parser.add_argument("--clear", action="store_true", help="Clear queue of all non-user entries")
    parser.add_argument("--detail", type=str, default=None, help="Detail text for new queue entries")
    args = parser.parse_args()

    if not args.heartbeat.exists():
        print(f"ERROR: HEARTBEAT not found: {args.heartbeat}", file=sys.stderr)
        return 1

    if args.clear:
        removed = clear_queue(args.heartbeat.resolve())
        print(f"project_insights: cleared {removed} non-user entries")
        return 0

    ptype = detect_project_type(args.project.resolve())
    print(f"[project_insights] type={ptype} lang={args.language}")

    if args.refresh:
        added = refresh_queue(args.project.resolve(), args.heartbeat.resolve(), args.language, args.min, args.detail)
        return 0 if added >= 0 else 1

    result = choose_best_candidate(args.project.resolve(), args.heartbeat.resolve(), args.language)
    if not result:
        print("project_insights: no new candidates found")
        return 0
    finding, _detail = result
    final_detail = args.detail if args.detail is not None else _detail
    return 0 if append_to_queue(args.heartbeat.resolve(), finding, final_detail) else 1


if __name__ == "__main__":
    raise SystemExit(main())