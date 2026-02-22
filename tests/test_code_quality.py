
import os
import ast
from pathlib import Path
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

def test_no_silent_except_pass():
    """
    Quality Gate: Fails if any 'try: ... except: pass' (or ...) blocks are found.
    Silent failures lead to hard-to-debug states. Use logging or explicit handling instead.
    """
    root_dir = Path(__file__).parent.parent
    py_files = get_python_files(root_dir)
    
    all_violations = []
    
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            visitor = SilentFailureVisitor(str(py_file.relative_to(root_dir)))
            visitor.visit(tree)
            all_violations.extend(visitor.violations)
        except Exception as e:
            # If we can't parse a file, we skip it (might be a template or invalid py)
            print(f"Skipping {py_file} due to parse error: {e}")
            
    if all_violations:
        msg = "\n".join([f"  - {f}:{l} -> Illegal 'except: pass' block found." for f, l in all_violations])
        pytest.fail(f"Quality Gate Failed: Silent exceptions detected!\n{msg}\n\nHint: Replace 'pass' with at least a logger.warning() or logger.debug() call.")

if __name__ == "__main__":
    # Allow running this script directly
    test_no_silent_except_pass()
