# Claude Workflows

Personal Claude Code development workflow toolkit. Portable skills, scripts, and configurations that follow me across projects.

## What's here

### Skills
| Skill | Purpose |
|-------|---------|
| `beads` | Beads issue tracking workflow — claim, track, close, remember |
| `plan-and-track` | Comprehensive planning + beads issue creation for significant work |

### Scripts
| Script | Purpose |
|--------|---------|
| `statusline.sh` | Custom Claude Code status bar — model, context %, waste factor, rate limits |
| `claude-session-audit.py` | Analyze all Claude Code session transcripts for quota optimization |

## Installation

Register as a Claude Code plugin marketplace:

```bash
# From within Claude Code
/plugin marketplace add ~/projects/oss/claude-workflows
/plugin install claude-workflows@claude-workflows
```

Or add to `~/.claude/settings.json` manually:

```json
{
  "enabledPlugins": {
    "claude-workflows@claude-workflows": true
  }
}
```

## Structure

```
claude-workflows/
├── .claude-plugin/
│   ├── plugin.json          # Plugin manifest
│   └── marketplace.json     # Marketplace definition
├── skills/
│   ├── beads/SKILL.md       # Beads workflow
│   └── plan-and-track/SKILL.md  # Planning workflow
├── scripts/
│   ├── statusline.sh        # Status bar (symlink from ~/.claude/)
│   └── claude-session-audit.py  # Session analysis
└── README.md
```

## Relationship to project-specific plugins

This repo contains **general workflow** skills that apply to any project. Project-specific skills (like Alora's `pipeline-investigation` or `code-review`) stay in their respective project plugins.

| Scope | Location | Example |
|-------|----------|---------|
| Personal (this repo) | `~/projects/oss/claude-workflows/` | beads, plan-and-track |
| Project-specific | `<project>/.claude/plugins/<name>/` | pipeline-investigation, code-review |
| Community (marketplace) | Installed via `/plugin` | anthropics/skills (document-skills) |
