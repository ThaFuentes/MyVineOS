import os
import ast


def get_imports_from_file(file_path):
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            # Handles: import os, sqlite3
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")

            # Handles: from flask import g, current_app
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join([alias.name for alias in node.names])
                imports.append(f"from {module} import {names}")

    except Exception as e:
        return [f"Error parsing: {e}"]

    return imports


def main():
    root_dir = ".."
    print(f"{'File Path':<60} | {'Imports'}")
    print("-" * 100)

    for root, dirs, files in os.walk(root_dir):
        # Skip virtual environments and git folders
        if any(x in root for x in ['venv', '.git', '__pycache__', '.pytest_cache']):
            continue

        for file in files:
            if file.endswith(".py") and file != "inspect_imports.py":
                full_path = os.path.join(root, file)
                file_imports = get_imports_from_file(full_path)

                if file_imports:
                    print(f"\n{full_path}")
                    for imp in file_imports:
                        print(f"  - {imp}")


if __name__ == "__main__":
    main()