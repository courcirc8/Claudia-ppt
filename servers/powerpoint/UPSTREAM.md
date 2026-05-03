# Upstream MCP server

This server was vendored into Claudia-ppt on 2026-05-03.

- **Origin remote**: https://github.com/GongRzhe/Office-PowerPoint-MCP-Server.git
- **Last upstream commit**: 2b8bde3 version = "2.0.6"

To re-sync upstream changes manually:

```bash
cd servers/powerpoint
git init
git remote add upstream https://github.com/GongRzhe/Office-PowerPoint-MCP-Server.git
git fetch upstream
# review with: git log upstream/main --oneline
```
