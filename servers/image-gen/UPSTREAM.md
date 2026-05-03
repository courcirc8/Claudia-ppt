# Upstream MCP server

This server was vendored into Claudia-ppt on 2026-05-03.

- **Origin remote**: git@github.com:courcirc8/image_gen.git
- **Last upstream commit**: 7dcdf4e model selection: auto-select between seedream-4.5 (visual) and gpt-image-2 (text/infographic)

To re-sync upstream changes manually:

```bash
cd servers/image-gen
git init
git remote add upstream git@github.com:courcirc8/image_gen.git
git fetch upstream
# review with: git log upstream/main --oneline
```
