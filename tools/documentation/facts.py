"""Facts for the documentation: metrics, duplicates, fan-in, router actions, settings, tests. Writes facts.json."""
import ast
import collections
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = sys.argv[1]
OUT = sys.argv[2]
cat = json.load(open(os.path.join(os.path.dirname(OUT), "catalogue.json"), encoding="utf-8"))
facts = {}

# metrics per module
metrics = []
for mod, e in cat.items():
    funcs = e["functions"] + [m for c in e["classes"] for m in c["methods"]]
    n = len(funcs)
    doc = sum(1 for f in funcs if f["doc"])
    longest = sorted(funcs, key=lambda f: -f["len"])[:1]
    metrics.append({"module": mod, "lines": e["lines"], "functions": n, "documented": doc,
                    "avg_len": round(sum(f["len"] for f in funcs) / n, 1) if n else 0,
                    "longest": f"{longest[0]['name']} ({longest[0]['len']})" if longest else ""})
facts["metrics"] = metrics

# longest functions overall
allf = []
for mod, e in cat.items():
    for f in e["functions"]:
        allf.append((f["len"], mod, f["name"], f["line"]))
    for c in e["classes"]:
        for m in c["methods"]:
            allf.append((m["len"], mod, c["name"] + "." + m["name"], m["line"]))
allf.sort(reverse=True)
facts["longest"] = allf[:20]
facts["over_100"] = sum(1 for x in allf if x[0] > 100)
facts["over_50"] = sum(1 for x in allf if x[0] > 50)
facts["total_funcs"] = len(allf)

# duplicates between main.py and service.py
m = {f["name"] for f in cat["main.py"]["functions"]}
s = {f["name"] for f in cat["service.py"]["functions"]}
facts["duplicates"] = sorted(m & s)

# fan-in inside main.py and service.py
for mod in ("main.py", "service.py"):
    cnt = collections.Counter()
    for f in cat[mod]["functions"]:
        for c in f["calls"]:
            cnt[c] += 1
    facts[f"fanin_{mod}"] = cnt.most_common(15)

# service -> plugin calls (plugin.<name>)
src = open(os.path.join(ROOT, "service.py"), encoding="utf-8").read()
facts["service_uses_plugin"] = sorted(set(re.findall(r"plugin\.([a-z_]+)\(", src)))

# router actions -> first function called in the branch
tree = ast.parse(open(os.path.join(ROOT, "main.py"), encoding="utf-8").read())
router = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "router")
actions = []
for node in ast.walk(router):
    if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
        t = node.test
        if isinstance(t.left, ast.Name) and t.left.id == "action" and isinstance(t.comparators[0], ast.Constant):
            calls = []
            for sub in node.body:
                for x in ast.walk(sub):
                    if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id not in ("str", "int", "len", "bool", "dict", "list", "float", "max", "min"):
                        calls.append(x.func.id)
            seen = []
            for cname in calls:
                if cname not in seen:
                    seen.append(cname)
            actions.append((t.comparators[0].value, seen[:3]))
facts["actions"] = actions

# settings
strings = {}
po = open(os.path.join(ROOT, "resources/language/resource.language.en_gb/strings.po"), encoding="utf-8").read()
for mid, text in re.findall(r'msgctxt "#(\d+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"', po):
    strings[mid] = text
root = ET.parse(os.path.join(ROOT, "resources/settings.xml")).getroot()
settings = []
for cat_el in root.iter("category"):
    for grp in cat_el.iter("group"):
        for st in grp.iter("setting"):
            default = st.find("default")
            settings.append({"category": strings.get(cat_el.get("label"), cat_el.get("id")),
                             "group": strings.get(grp.get("label") or "", ""),
                             "id": st.get("id"), "type": st.get("type"),
                             "label": strings.get(st.get("label") or "", ""),
                             "default": default.text if default is not None else ""})
facts["settings"] = settings

# tests
tests = []
for name in sorted(os.listdir(os.path.join(ROOT, "tests"))):
    if name.startswith("test_") and name.endswith(".py"):
        t = open(os.path.join(ROOT, "tests", name), encoding="utf-8").read()
        tests.append((name, len(re.findall(r"^\s+def test_", t, re.M)), len(re.findall(r"expectedFailure", t))))
facts["tests"] = tests

json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=1)
print(json.dumps({k: v for k, v in facts.items() if k in ("over_100", "over_50", "total_funcs", "duplicates", "service_uses_plugin")}, indent=0)[:3000])
print(facts["longest"][:12])
print(facts["fanin_main.py"])
print(len(facts["actions"]), facts["actions"][:5])
print(len(settings), settings[:3])
print(sum(t[1] for t in tests), [t for t in tests if t[2]])
