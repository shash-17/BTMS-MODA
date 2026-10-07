"""
Experiment 09 - SPC c-chart for the ACTUAL BTMS source modules.

Quality characteristic : static-analysis defects per source module
Defect definition      : every flake8 finding (pyflakes errors F*, pycodestyle
                         E/W, McCabe complexity C901 > 10), except E221
                         (intentional column alignment used throughout the code).
Observations           : modules in order of data flow through the system:
                         simulator -> ingestion -> ai_engine (detector, main)
                         -> auth_service -> dev_server
Outputs (this folder)  : spc_btms_modules_chart.png / _report.txt / _data.csv

Run: python3 spc_btms_modules.py      (needs: flake8, matplotlib)
"""
import csv
import math
import os
import subprocess
import sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    ("Simulator",         "simulator/simulator.py"),
    ("Ingestion",         "ingestion/app.py"),
    ("AI Anomaly Detector", "ai_engine/anomaly_detector.py"),
    ("AI Engine (main)",  "ai_engine/main.py"),
    ("Auth Service",      "auth_service/main.py"),
    ("Dev Server",        "dev_server.py"),
]

FLAKE8 = [sys.executable, "-m", "flake8", "--isolated", "--max-line-length=100",
          "--max-complexity=10", "--extend-ignore=E221"]


def analyse(path):
    out = subprocess.run(FLAKE8 + [path], cwd=HERE, capture_output=True, text=True).stdout
    findings = [ln for ln in out.splitlines() if ln.strip()]
    codes = Counter(ln.split()[1] for ln in findings)
    loc = sum(1 for _ in open(os.path.join(HERE, path), encoding="utf-8"))
    return findings, codes, loc


# Steps 1-3: collect observations
data = []
for name, path in MODULES:
    findings, codes, loc = analyse(path)
    data.append({"module": name, "path": path, "loc": loc, "c": len(findings),
                 "codes": codes, "findings": findings})

labels = [d["module"] for d in data]
c = [d["c"] for d in data]
n = len(c)

# Step 4: c-chart statistics
total = sum(c)
c_bar = total / n
sigma = math.sqrt(c_bar)
ucl = c_bar + 3 * sigma
raw_lcl = c_bar - 3 * sigma
lcl = max(0.0, raw_lcl)

# Step 6: signals
ooc = [(i + 1, labels[i], v) for i, v in enumerate(c) if v > ucl or v < lcl]


def longest_run(vals, cl):
    best = cur = side = 0
    for v in vals:
        s = (v > cl) - (v < cl)
        cur = cur + 1 if (s and s == side) else (1 if s else 0)
        side = s
        best = max(best, cur)
    return best


run = longest_run(c, c_bar)

# Step 5: plot
x = list(range(1, n + 1))
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.plot(x, c, marker="o", color="#1f4e9c", label="Defects (c)")
ax.axhline(c_bar, color="green", label=f"CL = {c_bar:.2f}")
ax.axhline(ucl, color="red", linestyle="--", label=f"UCL = {ucl:.2f}")
ax.axhline(lcl, color="red", linestyle="--", label=f"LCL = {lcl:.2f}")
for xi, v in zip(x, c):
    ax.annotate(str(v), (xi, v), textcoords="offset points", xytext=(0, 7), ha="center")
for k, (xi, _, v) in enumerate(ooc):
    ax.plot(xi, v, "rs", markersize=11, label="Out of control" if k == 0 else None)
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=20, ha="right")
ax.set_xlabel("BTMS source module")
ax.set_ylabel("Number of defects (c)")
ax.set_title("c-Chart: Static-Analysis Defects per BTMS Module")
ax.set_ylim(0, max(ucl, max(c)) + 3)
ax.grid(alpha=0.3)
ax.legend(loc="upper left")
fig.tight_layout()
png = os.path.join(HERE, "spc_btms_modules_chart.png")
fig.savefig(png, dpi=150)

with open(os.path.join(HERE, "spc_btms_modules_data.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["obs", "module", "file", "lines_of_code", "defects_c", "codes"])
    for i, d in enumerate(data, 1):
        w.writerow([i, d["module"], d["path"], d["loc"], d["c"],
                    " ".join(f"{k}x{v}" for k, v in sorted(d["codes"].items()))])

# Steps 7-8: report
L = ["=" * 78, "SPC c-CHART REPORT - BTMS ACTUAL PROJECT MODULES", "=" * 78,
     "Characteristic : static-analysis defects per source module",
     "Defect         : flake8 finding (F*, E/W, C901>10); E221 alignment ignored",
     "", f"{'Obs':>3}  {'Module':<20} {'File':<31} {'LOC':>4} {'c':>3}  Status",
     "-" * 78]
for i, d in enumerate(data, 1):
    st = "OUT OF CONTROL" if d["c"] > ucl or d["c"] < lcl else "within limits"
    L.append(f"{i:>3}  {d['module']:<20} {d['path']:<31} {d['loc']:>4} {d['c']:>3}  {st}")
L += ["", f"n = {n}    Sum(ci) = {total}",
      f"CL  = c-bar = {total}/{n} = {c_bar:.2f}",
      f"sqrt(c-bar) = {sigma:.3f}",
      f"UCL = c-bar + 3*sqrt(c-bar) = {ucl:.2f}",
      f"LCL = c-bar - 3*sqrt(c-bar) = {raw_lcl:.2f} -> {lcl:.2f}",
      "", f"Points outside limits         : {len(ooc)}",
      f"Longest run on one side of CL : {run}  (non-random if >= 7)", ""]
if ooc:
    L.append("SPECIAL-CAUSE SIGNALS:")
    for i, m, v in ooc:
        L.append(f"  Obs {i} ({m}): c = {v} > UCL {ucl:.2f}" if v > ucl
                 else f"  Obs {i} ({m}): c = {v} < LCL {lcl:.2f}")
    L += ["", "Interpretation: process NOT in statistical control; investigate flagged",
          "module(s) for assignable causes."]
else:
    L += ["Interpretation: all observations within limits; process in control."]
L += ["", "DEFECT BREAKDOWN PER MODULE:"]
for d in data:
    br = ", ".join(f"{k} x{v}" for k, v in sorted(d["codes"].items())) or "none"
    L.append(f"  {d['module']:<20}: {br}")
L += ["", "Code legend: E302/E305 blank-line spacing, E501 line too long, E402 import",
      "not at top, E127 continuation-line indent, F401 unused import.",
      "", "DETAILED FINDINGS FOR FLAGGED MODULES:"]
for _, m, _ in ooc:
    d = next(x for x in data if x["module"] == m)
    L.append(f"  [{m}]")
    L += [f"    {ln}" for ln in d["findings"]]
L += ["", "Note: modules differ in size (LOC column); a u-chart (defects/KLOC) would",
      "normalise this. The c-chart is used as the experiment requires.", "=" * 78]
report = "\n".join(L)
print(report)
with open(os.path.join(HERE, "spc_btms_modules_report.txt"), "w") as f:
    f.write(report + "\n")
print(f"\nChart saved: {png}")
