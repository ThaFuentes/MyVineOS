# Unrelated_Helper_Tools/find_flask_in_models.py
# One-time script to scan app/models/pastoral/ for leftover Flask / route imports
# that are causing circular imports.
# Run with: python Unrelated_Helper_Tools/find_flask_in_models.py
#          (from anywhere — it finds the folder relative to itself)

import os
import re
import sys

# Go up **one level** from this script's folder → should be project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)   # ← this is the key change

MODELS_DIR = os.path.join(PROJECT_ROOT, "app", "models", "pastoral")

if not os.path.isdir(MODELS_DIR):
    print(f"ERROR: Cannot find folder: {MODELS_DIR}")
    print("Expected structure:")
    print("  some_project_root/")
    print("  ├── app/")
    print("  │   └── models/")
    print("  │       └── pastoral/")
    print("  └── Unrelated_Helper_Tools/")
    print("      └── find_flask_in_models.py  ← this file")
    print(f"\nCurrent script location: {SCRIPT_DIR}")
    print(f"Calculated project root : {PROJECT_ROOT}")
    sys.exit(1)

# Patterns that should NOT exist in model files
DANGEROUS_PATTERNS = [
    r"from\s+flask\s+import",
    r"from\s+\.\s*import\s+pastoral_bp",
    r"from\s+\.\s*import\s+pastoral_required",
    r"@pastoral_required",
    r"Blueprint\s*\(",
    r"render_template",
    r"redirect",
    r"flash",
    r"session",
    r"jsonify",
    r"request\.",
]

print(f"Scanning folder: {MODELS_DIR}")
print("Looking for problematic Flask / routing code in model files...\n")

found_any = False

for filename in sorted(os.listdir(MODELS_DIR)):
    if not filename.endswith(".py") or filename == "__init__.py":
        continue

    filepath = os.path.join(MODELS_DIR, filename)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Could not read {filename}: {e}")
        continue

    matches = []
    for pattern in DANGEROUS_PATTERNS:
        for match in re.finditer(pattern, content, flags=re.MULTILINE):
            line_num = content[:match.start()].count("\n") + 1
            try:
                line = content.splitlines()[line_num - 1].strip()
            except IndexError:
                line = "<could not extract line>"
            matches.append((line_num, pattern, line))

    if matches:
        found_any = True
        print(f"PROBLEM DETECTED in: {filename}")
        for line_num, pattern, line in matches:
            print(f"  Line {line_num:4d} | Pattern: {pattern:<30} → {line}")
        print("-" * 80 + "\n")

if not found_any:
    print("✓ No problematic Flask/route-related code found in app/models/pastoral/*.py")
    print("  Models folder appears clean regarding circular import risks from Flask bits.")