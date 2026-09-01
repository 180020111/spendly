import sys
import json
import re

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")

db = "expense_tracker.db"
db_re = re.escape(db)

db_patterns = [
    r"\brm\b.*" + db_re,
    db_re + r".*\brm\b",
    r"\bunlink\b.*" + db_re,
    db_re + r".*\bunlink\b",
    r"\bshred\b.*" + db_re,
    r"\btruncate\b.*" + db_re,
    r"\bmv\b.*" + db_re,
    db_re + r".*\bmv\b",
    r"\bfind\b.*-delete.*" + db_re,
    r"\bfind\b.*" + db_re + r".*-delete",
    r">\s*" + db_re,
]
db_substrings = [
    "os.remove(",
    "os.unlink(",
    ".unlink()",
    "dd if",
    "of=" + db,
]


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    raise SystemExit(0)


db_matched = any(re.search(p, cmd) for p in db_patterns)
if not db_matched and db in cmd:
    db_matched = any(s in cmd for s in db_substrings)

if db_matched:
    deny(
        "CAUTION: This command would delete, truncate, move, or overwrite "
        "the protected database file '" + db + "'. Blocked by policy — "
        "if you really need to do this, remove the file manually outside "
        "Claude Code."
    )

protected = [".env", "migrations/"]
dangerous = ["rm ", "rm -", "unlink ", "truncate "]
for d in dangerous:
    if d in cmd:
        for p in protected:
            if p in cmd:
                deny(
                    "CAUTION: This command would run a destructive "
                    "operation on the protected path '" + p + "'. "
                    "Blocked by policy."
                )
