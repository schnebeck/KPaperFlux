"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           tools/clone_detector.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Claude Sonnet 4.6
Description:    AST-based code clone detector. Identifies Type-1 (exact),
                Type-2 (variable-renamed), and Type-3 (near-match) duplicates
                across all Python source files in the project.

Usage:
    python tools/clone_detector.py              # scan core/ and gui/
    python tools/clone_detector.py --all        # include tests/ tools/ plugins/
    python tools/clone_detector.py --threshold 0.90
------------------------------------------------------------------------------
"""

import ast
import hashlib
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_SCAN_DIRS = ["core", "gui", "plugins"]
ALL_SCAN_DIRS = ["core", "gui", "plugins", "tests", "tools"]

# Functions with fewer AST nodes are too trivial to report
MIN_NODES = 15

# Similarity threshold for Type-3 (near-clone) detection
DEFAULT_THRESHOLD = 0.87

# Only compare pairs where node counts are within this ratio (avoids O(n²) blowup)
SIZE_RATIO_MAX = 1.35

# Max tokens used in similarity comparison (caps cost for large functions)
MAX_TOKENS_FOR_SIM = 300


# ---------------------------------------------------------------------------
# AST Normalizer: converts a function body into a structure-only string
# by replacing all variable/arg names with positional placeholders and
# collapsing all literal values to their type markers.
# ---------------------------------------------------------------------------

class _Normalizer(ast.NodeVisitor):
    """Produces a canonical structural text from an AST subtree."""

    def __init__(self) -> None:
        self._var_map: Dict[str, str] = {}
        self._counter: int = 0
        self._parts: List[str] = []

    def _var(self, name: str) -> str:
        if name not in self._var_map:
            self._var_map[name] = f"$v{self._counter}"
            self._counter += 1
        return self._var_map[name]

    def _emit(self, *tokens: str) -> None:
        self._parts.extend(tokens)

    # --- Statements ---

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._emit("DEF(")
        for a in node.args.args:
            self._emit(f"ARG({self._var(a.arg)})")
        for stmt in node.body:
            self.visit(stmt)
        self._emit(")")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        self._emit("ASSIGN(")
        for t in node.targets:
            self.visit(t)
        self.visit(node.value)
        self._emit(")")

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._emit(f"AUG({type(node.op).__name__}(")
        self.visit(node.target)
        self.visit(node.value)
        self._emit("))")

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._emit("ANNASSIGN(")
        self.visit(node.target)
        if node.value:
            self.visit(node.value)
        self._emit(")")

    def visit_Return(self, node: ast.Return) -> None:
        self._emit("RETURN(")
        if node.value:
            self.visit(node.value)
        self._emit(")")

    def visit_If(self, node: ast.If) -> None:
        self._emit("IF(")
        self.visit(node.test)
        self._emit("THEN(")
        for s in node.body:
            self.visit(s)
        self._emit(")")
        if node.orelse:
            self._emit("ELSE(")
            for s in node.orelse:
                self.visit(s)
            self._emit(")")
        self._emit(")")

    def visit_For(self, node: ast.For) -> None:
        self._emit("FOR(")
        self.visit(node.target)
        self.visit(node.iter)
        for s in node.body:
            self.visit(s)
        self._emit(")")

    def visit_While(self, node: ast.While) -> None:
        self._emit("WHILE(")
        self.visit(node.test)
        for s in node.body:
            self.visit(s)
        self._emit(")")

    def visit_Try(self, node: ast.Try) -> None:
        self._emit("TRY(")
        for s in node.body:
            self.visit(s)
        for h in node.handlers:
            self._emit("EXCEPT(")
            for s in h.body:
                self.visit(s)
            self._emit(")")
        self._emit(")")

    def visit_With(self, node: ast.With) -> None:
        self._emit("WITH(")
        for item in node.items:
            self.visit(item.context_expr)
        for s in node.body:
            self.visit(s)
        self._emit(")")

    def visit_Raise(self, node: ast.Raise) -> None:
        self._emit("RAISE(")
        if node.exc:
            self.visit(node.exc)
        self._emit(")")

    def visit_Delete(self, node: ast.Delete) -> None:
        self._emit("DEL(")
        for t in node.targets:
            self.visit(t)
        self._emit(")")

    def visit_Pass(self, node: ast.Pass) -> None:
        self._emit("PASS")

    def visit_Break(self, node: ast.Break) -> None:
        self._emit("BREAK")

    def visit_Continue(self, node: ast.Continue) -> None:
        self._emit("CONTINUE")

    def visit_Expr(self, node: ast.Expr) -> None:
        self.visit(node.value)

    # --- Expressions ---

    def visit_Name(self, node: ast.Name) -> None:
        self._emit(self._var(node.id))

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self._emit("BOOL")
        elif isinstance(node.value, (int, float)):
            self._emit("NUM")
        elif isinstance(node.value, str):
            self._emit("STR")
        elif node.value is None:
            self._emit("NONE")
        else:
            self._emit("CONST")

    def visit_Call(self, node: ast.Call) -> None:
        self._emit("CALL(")
        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            self._emit(f"KW({kw.arg or '**'}=")
            self.visit(kw.value)
            self._emit(")")
        self._emit(")")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._emit("ATTR(")
        self.visit(node.value)
        self._emit(f".{node.attr})")

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self._emit(f"BIN({type(node.op).__name__}(")
        self.visit(node.left)
        self.visit(node.right)
        self._emit("))")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self._emit(f"UNARY({type(node.op).__name__}(")
        self.visit(node.operand)
        self._emit("))")

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self._emit(f"BOOLOP({type(node.op).__name__}(")
        for v in node.values:
            self.visit(v)
        self._emit("))")

    def visit_Compare(self, node: ast.Compare) -> None:
        self._emit("CMP(")
        self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            self._emit(type(op).__name__)
            self.visit(comp)
        self._emit(")")

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._emit("IFEXP(")
        self.visit(node.test)
        self.visit(node.body)
        self.visit(node.orelse)
        self._emit(")")

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._emit("SUB(")
        self.visit(node.value)
        self.visit(node.slice)
        self._emit(")")

    def visit_List(self, node: ast.List) -> None:
        self._emit("LIST(")
        for e in node.elts:
            self.visit(e)
        self._emit(")")

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._emit("TUPLE(")
        for e in node.elts:
            self.visit(e)
        self._emit(")")

    def visit_Dict(self, node: ast.Dict) -> None:
        self._emit("DICT(")
        for k, v in zip(node.keys, node.values):
            if k:
                self.visit(k)
            self.visit(v)
        self._emit(")")

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._emit("LAMBDA(")
        self.visit(node.body)
        self._emit(")")

    def generic_visit(self, node: ast.AST) -> None:
        self._emit(type(node).__name__)
        super().generic_visit(node)

    def get_text(self) -> str:
        return " ".join(self._parts)


# ---------------------------------------------------------------------------
# Function Extractor
# ---------------------------------------------------------------------------

class _FunctionExtractor(ast.NodeVisitor):
    """Walks a module AST and collects all function/method definitions."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.records: List[Dict] = []
        self._class_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node)
        # Recurse for nested classes but NOT nested functions
        # (nested functions get recorded separately via generic_visit)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record(self, node: ast.FunctionDef) -> None:
        nc = sum(1 for _ in ast.walk(node))
        if nc < MIN_NODES:
            return
        norm = _Normalizer()
        norm.visit(node)
        norm_text = norm.get_text()
        raw_text = ast.dump(node)
        self.records.append({
            "file": self.filepath,
            "line": node.lineno,
            "name": node.name,
            "class": self._class_stack[-1] if self._class_stack else None,
            "raw_hash": hashlib.md5(raw_text.encode()).hexdigest(),
            "norm_hash": hashlib.md5(norm_text.encode()).hexdigest(),
            "norm_text": norm_text,
            "node_count": nc,
        })


def _extract_from_file(filepath: Path) -> List[Dict]:
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"  [!] Parse error in {filepath}: {e}")
        return []
    extractor = _FunctionExtractor(str(filepath.relative_to(PROJECT_ROOT)))
    extractor.visit(tree)
    return extractor.records


def _collect_all(scan_dirs: List[str]) -> List[Dict]:
    all_records = []
    for d in scan_dirs:
        for py_file in sorted((PROJECT_ROOT / d).rglob("*.py")):
            all_records.extend(_extract_from_file(py_file))
    return all_records


# ---------------------------------------------------------------------------
# Clone Detection
# ---------------------------------------------------------------------------

def _label(rec: Dict) -> str:
    cls = f"{rec['class']}." if rec["class"] else ""
    return f"{rec['file']}:{rec['line']}  {cls}{rec['name']}()"


def find_clones(records: List[Dict], threshold: float) -> Dict[str, List]:
    """
    Returns three groups of findings:
      - type1: exact duplicates (identical AST dump)
      - type2: variable-renamed clones (same structure, different names)
      - type3: near-clones above the similarity threshold
    """
    # Type 1 — exact
    by_raw: Dict[str, List[Dict]] = defaultdict(list)
    for r in records:
        by_raw[r["raw_hash"]].append(r)
    type1 = {h: grp for h, grp in by_raw.items() if len(grp) > 1}

    # Type 2 — variable-renamed (same norm hash, different raw hash)
    by_norm: Dict[str, List[Dict]] = defaultdict(list)
    for r in records:
        if r["raw_hash"] not in type1:  # already reported as exact
            by_norm[r["norm_hash"]].append(r)
    type2 = {h: grp for h, grp in by_norm.items() if len(grp) > 1}

    # Type 3 — near-clones via SequenceMatcher
    # Only compare pairs not already in type1/type2 and with similar node counts.
    # Uses a two-stage filter to keep runtime manageable:
    #   Stage 1 (fast): Jaccard similarity on token sets — O(1) per pair
    #   Stage 2 (slow): full SequenceMatcher — only for pairs passing stage 1
    exact_ids = {id(r) for grp in type1.values() for r in grp}
    exact_ids |= {id(r) for grp in type2.values() for r in grp}
    candidates = [r for r in records if id(r) not in exact_ids]
    candidates.sort(key=lambda r: r["node_count"])

    # Pre-compute token sets for fast Jaccard pre-filter
    for r in candidates:
        tokens = r["norm_text"].split()[:MAX_TOKENS_FOR_SIM]
        r["_token_set"] = set(tokens)
        r["_tokens_trunc"] = " ".join(tokens)

    # Jaccard pre-filter threshold — set lower than final threshold to avoid
    # false negatives (Jaccard underestimates sequence similarity)
    jaccard_pre = max(0.0, threshold - 0.20)

    type3_pairs: List[Tuple[float, Dict, Dict]] = []
    seen_pairs = set()
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            if b["node_count"] > a["node_count"] * SIZE_RATIO_MAX:
                break  # sorted by size — no more matches possible
            pair_key = tuple(sorted([a["file"] + str(a["line"]), b["file"] + str(b["line"])]))
            if pair_key in seen_pairs:
                continue
            # Stage 1: fast Jaccard on token sets
            union = len(a["_token_set"] | b["_token_set"])
            if union == 0:
                continue
            jaccard = len(a["_token_set"] & b["_token_set"]) / union
            if jaccard < jaccard_pre:
                continue
            # Stage 2: precise sequence similarity on truncated tokens
            sim = SequenceMatcher(
                None, a["_tokens_trunc"], b["_tokens_trunc"], autojunk=False
            ).ratio()
            if sim >= threshold:
                seen_pairs.add(pair_key)
                type3_pairs.append((sim, a, b))

    type3_pairs.sort(key=lambda x: -x[0])

    return {"type1": type1, "type2": type2, "type3": type3_pairs}


# ---------------------------------------------------------------------------
# Report Printer
# ---------------------------------------------------------------------------

_SEP = "-" * 72

def _print_report(findings: Dict, threshold: float) -> int:
    """Prints findings and returns total clone pair count."""
    total = 0

    # --- Type 1 ---
    if findings["type1"]:
        print(f"\n{'='*72}")
        print(f"  TYPE 1 — EXACT DUPLICATES  ({len(findings['type1'])} group(s))")
        print(f"{'='*72}")
        for grp in findings["type1"].values():
            print(f"\n  [{grp[0]['node_count']} nodes]")
            for r in grp:
                print(f"    {_label(r)}")
            total += len(grp) - 1
    else:
        print("\n  [+] Type 1 (exact): none found")

    # --- Type 2 ---
    if findings["type2"]:
        print(f"\n{'='*72}")
        print(f"  TYPE 2 — VARIABLE-RENAMED CLONES  ({len(findings['type2'])} group(s))")
        print(f"{'='*72}")
        for grp in findings["type2"].values():
            print(f"\n  [{grp[0]['node_count']} nodes — same structure, different names]")
            for r in grp:
                print(f"    {_label(r)}")
            total += len(grp) - 1
    else:
        print("  [+] Type 2 (variable-renamed): none found")

    # --- Type 3 ---
    if findings["type3"]:
        print(f"\n{'='*72}")
        print(f"  TYPE 3 — NEAR-CLONES  (threshold ≥ {threshold:.0%}, {len(findings['type3'])} pair(s))")
        print(f"{'='*72}")
        for sim, a, b in findings["type3"]:
            print(f"\n  {sim:.1%} similar  [{a['node_count']} vs {b['node_count']} nodes]")
            print(f"    A: {_label(a)}")
            print(f"    B: {_label(b)}")
        total += len(findings["type3"])
    else:
        print(f"  [+] Type 3 (near-clones, ≥{threshold:.0%}): none found")

    return total


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    scan_all = "--all" in args
    threshold = DEFAULT_THRESHOLD
    for arg in args:
        if arg.startswith("--threshold="):
            threshold = float(arg.split("=")[1])
        elif arg.startswith("--threshold"):
            idx = args.index(arg)
            if idx + 1 < len(args):
                threshold = float(args[idx + 1])

    scan_dirs = ALL_SCAN_DIRS if scan_all else DEFAULT_SCAN_DIRS

    print(f"\nKPaperFlux Clone Detector")
    print(f"Scanning: {', '.join(scan_dirs)}")
    print(f"Min function size: {MIN_NODES} AST nodes")
    print(f"Near-clone threshold: {threshold:.0%}")
    print(_SEP)

    records = _collect_all(scan_dirs)
    print(f"  [*] Extracted {len(records)} functions from {len(scan_dirs)} directories")

    findings = find_clones(records, threshold)
    total = _print_report(findings, threshold)

    print(f"\n{_SEP}")
    if total == 0:
        print("  [ OK ] No clones detected.")
    else:
        print(f"  [!] {total} clone pair(s) detected — review recommended.")
    print()


if __name__ == "__main__":
    main()
