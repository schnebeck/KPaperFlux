"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tests/test_code_quality.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Tests: code quality.
------------------------------------------------------------------------------
"""

import ast
import re
from pathlib import Path
from typing import Optional

import pytest

class SilentFailureVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.violations = []

    def visit_ExceptHandler(self, node):
        # A "silent" handler is one where the body only contains 'pass' or '...'
        is_silent = True
        
        if not node.body:
            is_silent = True
        else:
            for stmt in node.body:
                # Check for 'pass'
                if isinstance(stmt, ast.Pass):
                    continue
                # Check for '...' (Ellipsis)
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
                    continue
                # If anything else is there (logger, print, return, raise, assignment)
                is_silent = False
                break
        
        if is_silent:
            self.violations.append((self.filename, node.lineno))
        
        self.generic_visit(node)

def get_python_files(root_dir):
    python_files = []
    # Relevant directories to scan
    include_dirs = ['core', 'gui', 'plugins', 'tools']
    
    for include_dir in include_dirs:
        dir_path = Path(root_dir) / include_dir
        if not dir_path.exists():
            continue
            
        for path in dir_path.rglob("*.py"):
            # Skip hidden files
            if any(part.startswith('.') for part in path.parts):
                continue
            python_files.append(path)
    return python_files

def test_no_bare_except():
    """
    Quality Gate: Fails on bare 'except:' clauses. They also catch KeyboardInterrupt
    and SystemExit and hide which errors a block really expects.
    """
    root_dir = Path(__file__).parent.parent
    violations = []
    for py_file in [*get_python_files(root_dir), root_dir / "main.py"]:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                violations.append(f"  - {py_file.relative_to(root_dir)}:{node.lineno}")
    if violations:
        pytest.fail("Quality Gate Failed: bare 'except:' found!\n" + "\n".join(violations)
                    + "\n\nHint: catch the specific exceptions the block expects.")


def test_no_silent_except_pass():
    """
    Quality Gate: Fails if any 'try: ... except: pass' (or ...) blocks are found.
    Silent failures lead to hard-to-debug states. Use logging or explicit handling instead.
    """
    root_dir = Path(__file__).parent.parent
    py_files = get_python_files(root_dir)
    
    all_violations = []
    
    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        visitor = SilentFailureVisitor(str(py_file.relative_to(root_dir)))
        visitor.visit(tree)
        all_violations.extend(visitor.violations)

    if all_violations:
        msg = "\n".join([f"  - {f}:{l} -> Illegal 'except: pass' block found." for f, l in all_violations])
        pytest.fail(f"Quality Gate Failed: Silent exceptions detected!\n{msg}\n\nHint: Replace 'pass' with at least a logger.warning() or logger.debug() call.")

class TrFstringVisitor(ast.NodeVisitor):
    """Detects self.tr(f"...") calls — f-strings inside tr() are invisible to pylupdate6."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list = []

    def visit_Call(self, node: ast.Call) -> None:
        # Match self.tr(...) or tr(...)
        is_tr_call = (
            isinstance(node.func, ast.Attribute) and node.func.attr == "tr"
        ) or (
            isinstance(node.func, ast.Name) and node.func.id == "tr"
        )
        if is_tr_call and node.args and isinstance(node.args[0], ast.JoinedStr):
            self.violations.append((self.filename, node.lineno))
        self.generic_visit(node)


def test_no_fstring_in_tr():
    """
    Quality Gate: Fails if any tr(f"...") calls are found.
    F-strings inside tr() are not extractable by pylupdate6 and break the
    l10n pipeline — the string will never appear in the .ts file.
    Use self.tr("Text with %s placeholder") % variable instead.
    """
    root_dir = Path(__file__).parent.parent
    py_files = get_python_files(root_dir)

    all_violations = []

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        visitor = TrFstringVisitor(str(py_file.relative_to(root_dir)))
        visitor.visit(tree)
        all_violations.extend(visitor.violations)

    if all_violations:
        msg = "\n".join([f"  - {f}:{l} -> tr(f\"...\") found." for f, l in all_violations])
        pytest.fail(
            f"Quality Gate Failed: f-strings inside tr() detected!\n{msg}\n\n"
            "Hint: Replace tr(f\"Text {{var}}\") with tr(\"Text %s\") % var"
        )


def test_pyflakes_clean():
    """
    Quality Gate: Fails on any pyflakes finding. Undefined names only raise NameError
    when the code path runs (e.g. a rarely used menu action); unused imports and
    variables, duplicate dict keys and broken format strings hide real mistakes.
    """
    from pyflakes.api import check
    from pyflakes.reporter import Reporter

    class _Collector(Reporter):
        def __init__(self) -> None:
            self.messages: list = []

        def flake(self, message) -> None:
            self.messages.append(message)

        def syntaxError(self, filename, msg, lineno, offset, text) -> None:
            self.messages.append(f"{filename}:{lineno}: syntax error: {msg}")

        def unexpectedError(self, filename, msg) -> None:
            self.messages.append(f"{filename}: {msg}")

    root_dir = Path(__file__).parent.parent
    collector = _Collector()
    test_files = sorted((root_dir / "tests").rglob("*.py"))
    for py_file in [*get_python_files(root_dir), root_dir / "main.py", *test_files]:
        check(py_file.read_text(encoding="utf-8"), str(py_file.relative_to(root_dir)), collector)

    if collector.messages:
        msg = "\n".join(f"  - {m}" for m in collector.messages)
        pytest.fail(f"Quality Gate Failed: pyflakes findings!\n{msg}")


def test_tr_uses_own_context():
    """
    Quality Gate: tr() must be called on the object itself (self.tr) or on a
    translator variable. self._parent.tr() / self.parent().tr() translate in the
    parent's context at runtime, while pylupdate files the string under the
    enclosing class, so the translation is never found.
    """
    root_dir = Path(__file__).parent.parent
    violations = []
    for py_file in get_python_files(root_dir):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "tr" and not isinstance(node.func.value, ast.Name)
                    and not (isinstance(node.func.value, ast.Call)
                             and getattr(node.func.value.func, "id", None) == "super")):
                violations.append(f"  - {py_file.relative_to(root_dir)}:{node.lineno}")
    if violations:
        pytest.fail("Quality Gate Failed: tr() called on another object (wrong l10n context)!\n"
                    + "\n".join(violations) + "\n\nHint: use self.tr() in a QObject subclass.")


UI_TEXT_SETTERS = {"setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setTitle", "showMessage",
                   "setStatusTip", "addAction", "addMenu"}
UI_TEXT_WIDGETS = {"QLabel", "QPushButton", "QCheckBox", "QGroupBox", "QAction", "QRadioButton", "QToolButton", "QMenu"}
# Literals that are not user-facing text
UI_TEXT_ALLOWED = {"KPaperFlux v2", "KPaperFlux_Page_Move", "iban, total_gross, …"}


def _literal_ui_text(node: ast.AST) -> Optional[str]:
    """The visible words of a string literal or f-string (HTML tags removed), if any."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    else:
        return None
    if text in UI_TEXT_ALLOWED:
        return None
    visible = re.sub(r"<[^>]*>", "", text)
    return text if re.search(r"[A-Za-zÄÖÜäöü]{3,}", visible) else None


def test_ui_text_is_translatable():
    """
    Quality Gate: user-facing text passed to widgets must go through tr().
    A literal in setText()/QLabel()/setToolTip() etc. stays English in every language.
    """
    root_dir = Path(__file__).parent.parent
    violations = []
    for base in ("gui", "plugins"):
        for py_file in sorted((root_dir / base).rglob("*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                if name in UI_TEXT_SETTERS or name in UI_TEXT_WIDGETS:
                    text = _literal_ui_text(node.args[0])
                    if text:
                        violations.append(f"  - {py_file.relative_to(root_dir)}:{node.lineno}: {name}({text[:50]!r})")
    if violations:
        pytest.fail("Quality Gate Failed: untranslated UI text!\n" + "\n".join(violations)
                    + "\n\nHint: wrap the text in self.tr().")


def test_files_have_project_header():
    """Quality Gate: every source file starts with the project header (see CLAUDE.md / coding rules)."""
    root_dir = Path(__file__).parent.parent
    files = [*get_python_files(root_dir), root_dir / "main.py", *sorted((root_dir / "tests").rglob("*.py"))]
    missing = [str(f.relative_to(root_dir)) for f in files
               if "Project:        KPaperFlux" not in f.read_text(encoding="utf-8")[:300]]
    if missing:
        pytest.fail("Quality Gate Failed: files without project header!\n" + "\n".join(f"  - {m}" for m in missing))


if __name__ == "__main__":
    # Allow running this script directly
    test_no_bare_except()
    test_no_silent_except_pass()
    test_no_fstring_in_tr()
    test_pyflakes_clean()
    test_tr_uses_own_context()
    test_ui_text_is_translatable()
    test_files_have_project_header()
