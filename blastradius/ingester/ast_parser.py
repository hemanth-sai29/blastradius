"""
AST Parser for BlastRadius.
Extracts files, classes, functions, calls, and imports from Python codebases.
"""

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedFunction:
    name: str
    full_name: str
    file_path: str
    class_name: str | None
    lineno: int
    end_lineno: int
    docstring: str = ""
    is_test: bool = False
    calls: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    name: str
    full_name: str
    file_path: str
    lineno: int
    end_lineno: int
    bases: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    module: str | None
    names: list[str] = field(default_factory=list)
    alias_map: dict[str, str] = field(default_factory=dict)  # name_used -> original_symbol
    level: int = 0


@dataclass
class ParsedFile:
    path: str
    name: str
    loc: int
    functions: list[ParsedFunction] = field(default_factory=list)
    classes: list[ParsedClass] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)


DEFAULT_IGNORES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    ".egg-info",
    "node_modules",
}


class CodeVisitor(ast.NodeVisitor):
    """Visits AST nodes to extract classes, functions, calls, and imports."""

    def __init__(self, rel_path: str):
        self.rel_path = rel_path.replace("\\", "/")
        self.functions: list[ParsedFunction] = []
        self.classes: list[ParsedClass] = []
        self.imports: list[ParsedImport] = []
        self._current_class: str | None = None
        self._current_function_calls: list[str] | None = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            alias_map = {alias.asname or alias.name: alias.name}
            self.imports.append(
                ParsedImport(
                    module=alias.name,
                    names=[alias.name],
                    alias_map=alias_map,
                    level=0,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        alias_map = {}
        names = []
        for alias in node.names:
            names.append(alias.name)
            alias_map[alias.asname or alias.name] = alias.name

        self.imports.append(
            ParsedImport(
                module=node.module,
                names=names,
                alias_map=alias_map,
                level=node.level or 0,
            )
        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        full_name = f"{self.rel_path}:{class_name}"
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        parsed_cls = ParsedClass(
            name=class_name,
            full_name=full_name,
            file_path=self.rel_path,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            bases=bases,
        )
        self.classes.append(parsed_cls)

        prev_class = self._current_class
        self._current_class = class_name
        self.generic_visit(node)
        self._current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        fn_name = node.name
        if self._current_class:
            full_name = f"{self.rel_path}:{self._current_class}.{fn_name}"
        else:
            full_name = f"{self.rel_path}:{fn_name}"

        docstring = ast.get_docstring(node) or ""
        is_test = (
            fn_name.startswith("test_")
            or "tests/" in self.rel_path
            or self.rel_path.startswith("test_")
        )

        prev_calls = self._current_function_calls
        self._current_function_calls = []

        # Visit the body to collect calls
        for item in node.body:
            self.visit(item)

        collected_calls = list(dict.fromkeys(self._current_function_calls))
        self._current_function_calls = prev_calls

        fn = ParsedFunction(
            name=fn_name,
            full_name=full_name,
            file_path=self.rel_path,
            class_name=self._current_class,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            docstring=docstring[:200],  # keep compact preview
            is_test=is_test,
            calls=collected_calls,
        )
        self.functions.append(fn)

    def visit_Call(self, node: ast.Call):
        call_name = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # E.g. self.connect() -> "connect" or obj.method() -> "method"
            call_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                # E.g. client.connect() -> "client.connect"
                call_name = f"{node.func.value.id}.{node.func.attr}"

        if call_name and self._current_function_calls is not None:
            self._current_function_calls.append(call_name)

        self.generic_visit(node)


class ASTParser:
    """Parses a codebase or single file into structured AST representation."""

    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()

    def parse_file(self, file_path: str | Path) -> ParsedFile | None:
        abs_path = (self.repo_root / file_path).resolve()
        if not abs_path.is_file() or not abs_path.name.endswith(".py"):
            return None

        try:
            rel_path = abs_path.relative_to(self.repo_root).as_posix()
        except ValueError:
            rel_path = abs_path.as_posix()

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(abs_path))
        except Exception:
            return None

        loc = len(content.splitlines())
        visitor = CodeVisitor(rel_path)
        visitor.visit(tree)

        return ParsedFile(
            path=rel_path,
            name=abs_path.name,
            loc=loc,
            functions=visitor.functions,
            classes=visitor.classes,
            imports=visitor.imports,
        )

    def parse_repo(
        self, ignore_patterns: set[str] | None = None
    ) -> list[ParsedFile]:
        """Walks repository and parses all non-ignored Python files."""
        ignores = DEFAULT_IGNORES | (ignore_patterns or set())
        parsed_files: list[ParsedFile] = []

        for root, dirs, files in os.walk(self.repo_root):
            # Prune ignored directories in place
            dirs[:] = [
                d
                for d in dirs
                if d not in ignores and not any(d.startswith(p) for p in ignores)
            ]

            for file in files:
                if file.endswith(".py"):
                    full_file_path = Path(root) / file
                    parsed = self.parse_file(full_file_path)
                    if parsed:
                        parsed_files.append(parsed)

        return parsed_files

    @staticmethod
    def resolve_imports(
        files: list[ParsedFile], repo_root: Path
    ) -> list[tuple[str, str]]:
        """
        Resolves IMPORTS relations: (source_file_path, target_file_path).
        """
        file_map = {f.path: f for f in files}
        resolved: set[tuple[str, str]] = set()

        for parsed_file in files:
            src_path = parsed_file.path
            src_dir = Path(src_path).parent

            for imp in parsed_file.imports:
                target_path = None

                # Handle relative imports: from .schema import ...
                if imp.level > 0 and imp.module:
                    # Move up (imp.level - 1) dirs
                    curr = src_dir
                    for _ in range(imp.level - 1):
                        curr = curr.parent
                    rel_candidate = (curr / f"{imp.module.replace('.', '/')}.py").as_posix()
                    if rel_candidate in file_map:
                        target_path = rel_candidate
                elif imp.level > 0 and not imp.module:
                    # e.g. from . import something
                    rel_candidate = (src_dir / "__init__.py").as_posix()
                    if rel_candidate in file_map:
                        target_path = rel_candidate
                elif imp.module:
                    # Absolute module path inside repo: e.g. blastradius.config
                    module_as_path = imp.module.replace(".", "/")
                    candidate1 = f"{module_as_path}.py"
                    candidate2 = f"{module_as_path}/__init__.py"

                    if candidate1 in file_map:
                        target_path = candidate1
                    elif candidate2 in file_map:
                        target_path = candidate2
                    else:
                        # Check partial path match
                        for path in file_map:
                            if path.endswith(candidate1) or path == candidate1:
                                target_path = path
                                break

                if target_path and target_path != src_path:
                    resolved.add((src_path, target_path))

        return list(resolved)

    @staticmethod
    def resolve_calls(
        files: list[ParsedFile],
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        Resolves CALLS and TESTS relationships.
        Returns:
            calls: list of (caller_full_name, callee_full_name)
            tests: list of (test_func_full_name, target_func_full_name)
        """
        # Build symbol lookup tables
        funcs_by_fullname: dict[str, ParsedFunction] = {}
        funcs_by_shortname: dict[str, list[ParsedFunction]] = {}
        funcs_by_file_shortname: dict[tuple[str, str], ParsedFunction] = {}
        classes_by_name: dict[str, list[ParsedClass]] = {}

        for f in files:
            for cls in f.classes:
                classes_by_name.setdefault(cls.name, []).append(cls)
            for fn in f.functions:
                funcs_by_fullname[fn.full_name] = fn
                funcs_by_shortname.setdefault(fn.name, []).append(fn)
                funcs_by_file_shortname[(f.path, fn.name)] = fn

        calls_set: set[tuple[str, str]] = set()
        tests_set: set[tuple[str, str]] = set()

        for f in files:
            # Map imported names to file/module
            import_symbol_to_file: dict[str, str] = {}
            for imp in f.imports:
                for used_name, orig_sym in imp.alias_map.items():
                    # If imported from module, map orig_sym
                    if imp.module:
                        mod_path = imp.module.replace(".", "/")
                        for p in files:
                            if p.path.startswith(mod_path) or p.path.endswith(f"{mod_path}.py"):
                                import_symbol_to_file[used_name] = p.path

            for caller in f.functions:
                for raw_call in caller.calls:
                    target_fn: ParsedFunction | None = None
                    call_token = raw_call.split(".")[-1]

                    # 1. Same-file local function
                    if (f.path, call_token) in funcs_by_file_shortname:
                        target_fn = funcs_by_file_shortname[(f.path, call_token)]

                    # 2. Same-class method (e.g. self.connect())
                    elif caller.class_name and raw_call.startswith("self."):
                        method_full = f"{f.path}:{caller.class_name}.{call_token}"
                        if method_full in funcs_by_fullname:
                            target_fn = funcs_by_fullname[method_full]

                    # 3. Explicitly imported symbol
                    elif call_token in import_symbol_to_file:
                        target_file = import_symbol_to_file[call_token]
                        if (target_file, call_token) in funcs_by_file_shortname:
                            target_fn = funcs_by_file_shortname[(target_file, call_token)]

                    # 4. Global match if unambiguous
                    elif call_token in funcs_by_shortname:
                        candidates = funcs_by_shortname[call_token]
                        if len(candidates) == 1:
                            target_fn = candidates[0]
                        else:
                            # Prefer non-test functions
                            non_tests = [c for c in candidates if not c.is_test]
                            if len(non_tests) == 1:
                                target_fn = non_tests[0]

                    # If resolved and not self-recursive to same node
                    if target_fn and target_fn.full_name != caller.full_name:
                        calls_set.add((caller.full_name, target_fn.full_name))

                        # If caller is a test function and callee is not a test
                        if caller.is_test and not target_fn.is_test:
                            tests_set.add((caller.full_name, target_fn.full_name))

                # Heuristic test mapping: test_login -> login
                if caller.is_test and caller.name.startswith("test_"):
                    target_name = caller.name[5:]  # remove "test_"
                    if target_name in funcs_by_shortname:
                        for candidate in funcs_by_shortname[target_name]:
                            if not candidate.is_test:
                                tests_set.add((caller.full_name, candidate.full_name))

        return list(calls_set), list(tests_set)
