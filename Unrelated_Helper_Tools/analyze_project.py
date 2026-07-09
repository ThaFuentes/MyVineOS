import ast
import re
import json
from pathlib import Path
from collections import defaultdict

# Set ROOT to one level higher than the script's directory
ROOT = Path(__file__).resolve().parents[1]
script_dir_name = Path(__file__).parent.name

print("PROJECT ANALYSIS TOOL v15.2 - Finalized with Full Static Detection")
print("=" * 70)
print(f"Root: {ROOT}")
print(f"Ignoring script directory: {script_dir_name}")
print()

# =============================================
# IGNORE LOGIC
# =============================================
IGNORE_DIRS = {
    ".git", ".idea", ".venv", "__pycache__", "instance", "node_modules",
    "dist", "build", ".pytest_cache", ".mypy_cache", "htmlcov", script_dir_name,
    ".vscode", "venv"
}
IGNORE_FILES = {
    ".gitignore", ".env", "requirements.txt", "project_structure.txt", "analysis_data.json"
}
IGNORE_SUFFIXES = {".pyc", ".log", ".db", ".sqlite3"}


def should_ignore(path: Path) -> bool:
    if any(ign in path.parts for ign in IGNORE_DIRS):
        return True
    if path.name in IGNORE_DIRS or path.name in IGNORE_FILES:
        return True
    if path.suffix in IGNORE_SUFFIXES:
        return True
    if any(part.startswith('.') for part in path.parts if part != '.'):
        return True
    return False


# =============================================
# HELPERS
# =============================================
def get_top_level_imports(content: str):
    try:
        root = ast.parse(content)
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name:
                    found.add(n.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split('.')[0])
    return found


def count_real_code_lines(content: str) -> int:
    if not content:
        return 0
    count = 0
    inside_docstring = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(('"""', "'''")):
            inside_docstring = not inside_docstring
            continue
        if inside_docstring or stripped.startswith("#"):
            continue
        count += 1
    return count


def extract_formatted_comments(content: str, rel_path: str):
    comment_block = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            comment_block.append(stripped.lstrip('#').strip())
        elif stripped:
            break
    if not comment_block:
        return None
    full_text = " ".join(comment_block)
    purpose_match = re.search(r"Purpose:\s*(.*)", full_text, re.IGNORECASE)
    purpose_content = purpose_match.group(1).strip() if purpose_match else full_text
    purpose_content = re.sub(r"^Purpose:\s*", "", purpose_content, flags=re.IGNORECASE).strip()
    block = [
        "===========================================================",
        f"File: {rel_path}",
        f"Path: {ROOT.name}/{rel_path}",
        f"Purpose: {purpose_content}",
        ""
    ]
    return "\n".join(block)


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return sorted(list(obj))
        return super().default(obj)


# =============================================
# CLEAN PROJECT TREE STRUCTURE
# =============================================
structure = ["CLEAN PROJECT STRUCTURE", "=" * 60, f"Root: {ROOT.name}/", ""]


def build_clean_tree(dir_path: Path, prefix: str = ""):
    if should_ignore(dir_path):
        return []
    entries = [p for p in dir_path.iterdir() if not should_ignore(p)]
    entries = sorted(entries, key=lambda p: (not p.is_file(), p.name.lower()))
    lines = []
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        pointer = "└── " if is_last else "├── "
        lines.append(f"{prefix}{pointer}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            lines.extend(build_clean_tree(entry, prefix + extension))
    return lines


structure.extend(build_clean_tree(ROOT))

# =============================================
# SINGLE-PASS DATA COLLECTION
# =============================================
project_data = {
    "python": [],
    "templates": [],
    "static": [],
    "references": {
        "py_imports": defaultdict(int),
        "templates": set(),
        "static": set(),
    },
    "entry_points": [],
    "comments.html": []
}
all_py_stems = set()
all_py_contents = {}

for fpath in ROOT.rglob("*"):
    if should_ignore(fpath) or not fpath.is_file():
        continue
    rel_path_posix = fpath.relative_to(ROOT).as_posix()

    if fpath.suffix == '.py':
        stem = fpath.stem
        all_py_stems.add(stem)
        try:
            content = fpath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            content = ""
        all_py_contents[rel_path_posix] = content

        is_entry = bool(re.search(r'if\s*__name__\s*==\s*["\']__main__[\'"]\s*:', content))
        if is_entry:
            project_data["entry_points"].append(rel_path_posix)

        import_refs = get_top_level_imports(content)
        has_routes = bool(re.search(r'@\w*\.route', content))
        creates_flask = bool(re.search(r'Flask\s*\(', content))
        defines_bp = bool(re.search(r'Blueprint\s*\(', content))

        for t in re.findall(r'render_template\s*\(\s*["\']([^"\']+\.html?)["\']', content):
            project_data["references"]["templates"].add(t.lstrip('/'))
        for s in re.findall(r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]", content):
            project_data["references"]["static"].add(s)

        formatted_block = extract_formatted_comments(content, rel_path_posix)
        if formatted_block:
            project_data["comments.html"].append(formatted_block)

        project_data["python"].append({
            "rel_path": rel_path_posix,
            "stem": stem,
            "content": content,
            "import_refs": import_refs,
            "is_entry": is_entry,
            "has_routes": has_routes,
            "creates_flask": creates_flask,
            "defines_bp": defines_bp,
        })

# Templates
templates_dir = next((d for d in [ROOT / "templates", ROOT / "app" / "templates"] if d.exists() and d.is_dir()), None)
templates_folder_rel = None
if templates_dir:
    templates_folder_rel = templates_dir.relative_to(ROOT).as_posix()
    for tpath in templates_dir.glob("**/*.html"):
        if tpath.is_file():
            rel = tpath.relative_to(templates_dir).as_posix()
            project_data["templates"].append({"rel_path": rel, "used": False})
            try:
                content = tpath.read_text(encoding='utf-8', errors='ignore')
                for _command, path in re.findall(r'{%\s*(include|extends)\s*["\']([^"\']+)["\']\s*%}', content):
                    project_data["references"]["templates"].add(path.lstrip('/'))
                for s in re.findall(r'(?:href|src)=["\']/static/([^"\'>]+)["\']', content):
                    project_data["references"]["static"].add(s)
                for s in re.findall(
                        r'{{\s*url_for\s*\(\s*[\'"]static[\'"]\s*,\s*filename\s*=\s*[\'"]([^\'"]+)[\'"]\s*\)\s*}}',
                        content):
                    project_data["references"]["static"].add(s)
            except Exception:
                pass

# Static
static_dir = next((d for d in [ROOT / "static", ROOT / "app" / "static"] if d.exists() and d.is_dir()), None)
static_folder_rel = None
if static_dir:
    static_folder_rel = static_dir.relative_to(ROOT).as_posix()
    for spath in static_dir.glob("**/*"):
        if spath.is_file() and spath.suffix:
            rel = spath.relative_to(static_dir).as_posix()
            project_data["static"].append({"rel_path": rel, "used": False})


# =============================================
# SMART TEMPLATE USAGE DETECTION
# =============================================
def collect_all_template_references():
    used = set(project_data["references"]["templates"])
    for tpath in ROOT.rglob("**/*.html"):
        if should_ignore(tpath):
            continue
        try:
            content = tpath.read_text(encoding='utf-8', errors='ignore')
            for match in re.findall(r'{%\s*(?:extends|include)\s*["\']([^"\']+)["\']', content):
                used.add(match.lstrip('/'))
            for match in re.findall(r'["\']([^"\']+\.html?)["\']', content):
                if match.endswith('.html'):
                    used.add(match.lstrip('/'))
        except Exception:
            pass
    return used


all_used_templates = collect_all_template_references()


# =============================================
# SMART STATIC ASSET DETECTION (v15.2 - FULL HTML SCAN)
# =============================================
def collect_all_static_references():
    used = set(project_data["references"]["static"])

    for tpath in ROOT.rglob("**/*.html"):
        if should_ignore(tpath):
            continue
        try:
            content = tpath.read_text(encoding='utf-8', errors='ignore')

            # Direct href/src to /static/ or static/
            for match in re.findall(r'(?:href|src)=["\'](/static/[^"\'>]+)["\']', content):
                used.add(match.lstrip('/'))
            for match in re.findall(r'(?:href|src)=["\'](static/[^"\'>]+)["\']', content):
                used.add(match)

            # Jinja url_for('static', filename='...')
            for match in re.findall(r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]",
                                    content):
                used.add(f"static/{match}")

            # CSS url() background images
            for match in re.findall(r'url\(["\']?(/static/[^"\')]+)["\']?\)', content):
                used.add(match.lstrip('/'))
            for match in re.findall(r'url\(["\']?(static/[^"\')]+)["\']?\)', content):
                used.add(match)

        except Exception:
            pass
    return used


all_used_static = collect_all_static_references()

# =============================================
# ANALYSIS PHASE
# =============================================
for py_info in project_data["python"]:
    for ref_mod in py_info["import_refs"]:
        if ref_mod in all_py_stems and ref_mod != "app":
            project_data["references"]["py_imports"][ref_mod] += 1

# Mark used templates
for t in project_data["templates"]:
    t["used"] = t["rel_path"] in all_used_templates

# Mark used static files (v15.2)
static_paths = {s["rel_path"] for s in project_data["static"]}
for s in project_data["static"]:
    s["used"] = s["rel_path"] in all_used_static

# Smart Python usage
used_py = set()
for py_info in project_data["python"]:
    path = py_info["rel_path"]
    if (py_info["is_entry"] or
            py_info["defines_bp"] or
            py_info["has_routes"] or
            py_info["creates_flask"] or
            "routes/" in path or
            "models/" in path or
            "builddb/" in path or
            "utils/" in path):
        used_py.add(path)
        pkg = Path(path).parent.as_posix()
        for other in project_data["python"]:
            if other["rel_path"].startswith(pkg + "/"):
                used_py.add(other["rel_path"])

# LOC & status
total_lines = 0
for py_info in project_data["python"]:
    content = py_info["content"]
    loc = count_real_code_lines(content)
    total_lines += loc
    py_info["loc"] = loc
    if py_info["rel_path"] in used_py:
        py_info["status"] = ["actively used (modular route / model)"]
    else:
        refs = project_data["references"]["py_imports"][py_info["stem"]]
        status = []
        if refs > 0:
            status.append(f"imported {refs} time{'s' if refs > 1 else ''}")
        if py_info["has_routes"]:
            status.append("defines routes")
        if py_info["creates_flask"]:
            status.append("creates Flask app")
        if py_info["defines_bp"]:
            status.append("defines blueprint")
        if py_info["is_entry"]:
            status.append("entry point")
        py_info["status"] = status or ["possibly unused"]

# Dynamic builddb heuristic
builddb_py = next((p for p in project_data["python"] if p["rel_path"] == "app/builddb/builddb.py"), None)
if builddb_py and builddb_py["status"] != ["possibly unused"]:
    for py_info in project_data["python"]:
        if py_info["rel_path"].startswith("app/builddb/") and py_info["rel_path"] != "app/builddb/builddb.py":
            if py_info["status"] == ["possibly unused"]:
                py_info["status"] = ["dynamically loaded by builddb.py"]

# =============================================
# REPORT GENERATION
# =============================================
line_report = ["REAL CODE LINE COUNTS & USAGE", "=" * 60]
py_sorted = sorted(project_data["python"], key=lambda x: x["rel_path"])
for py_info in py_sorted:
    if py_info["status"] == ["possibly unused"]:
        status_str = " (possibly unused)"
    else:
        status_str = " (" + ", ".join(py_info["status"]) + ")"
    line_report.append(f"{py_info['rel_path']}: {py_info['loc']} lines{status_str}")
line_report.extend(["", f"TOTAL EXECUTABLE PYTHON LINES: {total_lines}", ""])

usage_report = ["\nUSAGE ANALYSIS", "=" * 60,
                "Note: v15.2 - Full static asset detection from HTML + Python (v15.1 smart Python + template detection).",
                ""]
unused_py = [p["rel_path"] for p in py_sorted if p["status"] == ["possibly unused"]]
used_py_count = len(py_sorted) - len(unused_py)
usage_report.append(f"PYTHON FILES: {used_py_count}/{len(py_sorted)} appear used")
if unused_py:
    usage_report.append("\nPossibly unused Python files:")
    for u in sorted(unused_py):
        usage_report.append(f" - {u}")
else:
    usage_report.append("\nAll Python files appear used!")

if templates_dir:
    used_t = sum(1 for t in project_data["templates"] if t["used"])
    total_t = len(project_data["templates"])
    usage_report.append(f"\nTEMPLATES (in {templates_folder_rel}): {used_t}/{total_t} appear referenced")
    unused_t = sorted(t["rel_path"] for t in project_data["templates"] if not t["used"])
    if unused_t:
        usage_report.append("\nPossibly unused templates:")
        for u in unused_t:
            usage_report.append(f" - {templates_folder_rel}/{u}")
    else:
        usage_report.append("\nAll templates appear referenced!")
else:
    usage_report.append("\nTEMPLATES: No templates folder found")

if static_dir:
    used_s = sum(1 for s in project_data["static"] if s["used"])
    total_s = len(project_data["static"])
    usage_report.append(f"\nSTATIC FILES (in {static_folder_rel}): {used_s}/{total_s} appear referenced")
    unused_s = sorted(s["rel_path"] for s in project_data["static"] if not s["used"])
    if unused_s:
        usage_report.append("\nPossibly unused static files:")
        for u in unused_s:
            usage_report.append(f" - {static_folder_rel}/{u}")
    else:
        usage_report.append("\nAll static files appear referenced!")
else:
    usage_report.append("\nSTATIC FILES: No static folder found")


# Requirements
def generate_requirements(py_infos):
    package_mapping = {
        "docx": "python-docx", "yaml": "pyyaml", "PIL": "Pillow",
        "cv2": "opencv-python", "dotenv": "python-dotenv", "sklearn": "scikit-learn",
        "werkzeug": "Werkzeug", "bs4": "beautifulsoup4"
    }
    stdlib = {
        "os", "sys", "pathlib", "json", "datetime", "collections", "re",
        "math", "random", "sqlite3", "smtplib", "email", "traceback",
        "typing", "functools", "importlib", "pkgutil", "string", "abc",
        "time", "hashlib", "base64", "threading", "logging", "io", "csv",
        "urllib", "http", "socket", "subprocess", "argparse", "configparser"
    }
    local_stems = {p["stem"] for p in py_infos}
    dependencies = set()
    for py_info in py_infos:
        for mod in py_info["import_refs"]:
            if mod not in stdlib and mod not in local_stems and mod != "app":
                dependencies.add(package_mapping.get(mod, mod))
    return sorted(list(dependencies))


req_list = generate_requirements(project_data["python"])
req_report = ["\nGENERATED REQUIREMENTS.TXT", "=" * 60] + (
    req_list if req_list else ["# No external dependencies detected"]) + [""]

# Clean JSON
clean_data = {
    "python": [
        {k: v for k, v in py.items() if k != "content"}
        for py in project_data["python"]
    ],
    "templates": project_data["templates"],
    "static": project_data["static"],
    "references": {
        "py_imports": dict(project_data["references"]["py_imports"]),
        "templates": sorted(list(project_data["references"]["templates"])),
        "static": sorted(list(project_data["references"]["static"])),
    },
    "entry_points": project_data["entry_points"],
    "comments.html": project_data["comments.html"]
}
with open(ROOT / "analysis_data.json", "w", encoding="utf-8") as f:
    json.dump(clean_data, f, indent=2, cls=SetEncoder)

# Final consolidated report
with open(ROOT / "project_structure.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(
        line_report +
        usage_report +
        req_report +
        structure +
        ["\n\nFILE COMMENT BLOCKS (top-of-file # comments.html)", "=" * 60] +
        project_data["comments.html"]
    ))

with open(ROOT / "requirements.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(req_list) + "\n")

print("Analysis Complete!")
print("→ v15.2 Finalized with FULL static asset detection from HTML files")
print("→ All outputs written to project root")
