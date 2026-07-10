import argparse
import ast
from pathlib import Path

DEFAULT_MAX_FILE_LINES = 500
DEFAULT_MAX_OBJECT_LINES = 70
APP_DIR = Path("app")


def iter_python_files() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def file_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def collect_large_files(max_lines: int) -> list[tuple[int, Path]]:
    rows = [(file_line_count(path), path) for path in iter_python_files()]
    return sorted((row for row in rows if row[0] > max_lines), reverse=True)


def collect_large_objects(max_lines: int) -> list[tuple[int, str, Path, str, int, int]]:
    large: list[tuple[int, str, Path, str, int, int]] = []
    for path in iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            end = getattr(node, "end_lineno", node.lineno)
            size = end - node.lineno + 1
            if size > max_lines:
                large.append((size, type(node).__name__, path, node.name, node.lineno, end))
    return sorted(large, reverse=True)


def collect_forbidden_imports() -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        current_module = path.parts[2] if len(path.parts) > 3 and path.parts[1] == "modules" else ""
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module
            if not module.startswith("app.modules."):
                continue
            parts = module.split(".")
            imported_module = parts[2] if len(parts) > 2 else ""
            if imported_module == current_module:
                continue
            if module.endswith(".servico") or any(alias.name == "servico" for alias in node.names):
                findings.append((path, node.lineno, module))
    return findings


def print_report(max_file_lines: int, max_object_lines: int) -> int:
    large_files = collect_large_files(max_file_lines)
    large_objects = collect_large_objects(max_object_lines)
    forbidden_imports = collect_forbidden_imports()

    print(f"Large files > {max_file_lines} lines")
    for lines, path in large_files:
        print(f"{lines:5} {path}")

    print(f"\nLarge functions/classes > {max_object_lines} lines")
    for size, kind, path, name, start, end in large_objects:
        print(f"{size:5} {kind:16} {path}:{start}-{end} {name}")

    print("\nCross-module service imports")
    for path, line, module in forbidden_imports:
        print(f"{path}:{line} imports {module}")

    return len(large_files) + len(large_objects) + len(forbidden_imports)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-file-lines", type=int, default=DEFAULT_MAX_FILE_LINES)
    parser.add_argument("--max-object-lines", type=int, default=DEFAULT_MAX_OBJECT_LINES)
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()

    findings = print_report(args.max_file_lines, args.max_object_lines)
    return 1 if args.fail and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
