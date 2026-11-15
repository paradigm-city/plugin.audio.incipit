"""Extract a method catalogue from the add-on's Python sources: module docstring, classes, functions, signatures,
first docstring paragraph, line counts, internal imports and internal call graph (approximate)."""
import ast
import json
import os
import sys

ROOT = sys.argv[1]
OUT = sys.argv[2]
FILES = []
for base in ("", "mixassist", "soundprint"):
    folder = os.path.join(ROOT, base)
    for name in sorted(os.listdir(folder)):
        if name.endswith(".py"):
            FILES.append(os.path.join(base, name) if base else name)
for name in sorted(os.listdir(os.path.join(ROOT, "tools"))):
    if name.endswith(".py"):
        FILES.append(os.path.join("tools", name))

INTERNAL = {"main", "service", "logs", "context_mix", "context_radio", "musicip_dormant", "mixassist", "soundprint"}


def first_par(doc):
    if not doc:
        return ""
    return " ".join(doc.strip().split("\n\n")[0].split())


def sig(node):
    a = node.args
    parts = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(arg.arg + ("=" + ast.unparse(d) if d is not None else ""))
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    s = ", ".join(parts)
    if len(s) > 90:
        s = s[:87] + "..."
    return s


result = {}
for rel in FILES:
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as h:
        src = h.read()
    tree = ast.parse(src)
    mod = rel.replace("\\", "/")
    entry = {"doc": first_par(ast.get_docstring(tree)), "lines": src.count("\n") + 1, "functions": [],
             "classes": [], "imports": set(), "constants": []}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] in INTERNAL:
                    entry["imports"].add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in INTERNAL:
            entry["imports"].add(node.module)
    entry["imports"] = sorted(entry["imports"])
    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in defined and sub.func.id != node.name:
                    calls.add(sub.func.id)
            entry["functions"].append({"name": node.name, "sig": sig(node), "line": node.lineno,
                                       "len": node.end_lineno - node.lineno + 1,
                                       "doc": first_par(ast.get_docstring(node)), "calls": sorted(calls)})
        elif isinstance(node, ast.ClassDef):
            methods = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({"name": sub.name, "sig": sig(sub), "line": sub.lineno,
                                    "len": sub.end_lineno - sub.lineno + 1, "doc": first_par(ast.get_docstring(sub))})
            entry["classes"].append({"name": node.name, "line": node.lineno, "doc": first_par(ast.get_docstring(node)),
                                     "bases": [ast.unparse(b) for b in node.bases], "methods": methods})
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            n = node.targets[0].id
            if n.isupper():
                entry["constants"].append(n)
    result[mod] = entry

with open(OUT, "w", encoding="utf-8") as h:
    json.dump(result, h, indent=1)

# summary to stdout
tot = 0
for mod, e in result.items():
    nf = len(e["functions"]) + sum(len(c["methods"]) for c in e["classes"])
    tot += nf
    nodoc = sum(1 for f in e["functions"] if not f["doc"])
    print(f"{mod:32} lines={e['lines']:5} funcs={nf:4} nodoc={nodoc:4} imports={e['imports']}")
print("total callables", tot)
