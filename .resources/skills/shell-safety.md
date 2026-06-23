---
id: "shell-safety"
version: "1.0.0"
tags: [shell, terminal, safety]
applies-to: "**"
---

# Shell Safety

Never use heredoc (`<<EOF`) in terminal commands — special chars get mangled.

- **Write files:** Use `create_file` tool, not `cat <<EOF`
- **gh --body:** `create_file` → `--body-file /tmp/body.md && rm /tmp/body.md`
- **Multi-line args:** Write to file first, reference it
