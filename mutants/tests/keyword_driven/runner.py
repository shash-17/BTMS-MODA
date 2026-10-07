"""
runner.py  — Keyword-Driven Test Runner for BTMS
─────────────────────────────────────────────────────────────────────
Reads test_suite.csv, maps keyword strings to functions in keywords.py,
executes each test, and prints a colour-coded report with a summary.

Usage:
    python tests/keyword_driven/runner.py
    python tests/keyword_driven/runner.py --csv path/to/custom.csv
    python tests/keyword_driven/runner.py --report tests/reports/kdt_report.txt
"""

import csv
import os
import sys
import argparse
import datetime
from pathlib import Path

# ── Colour helpers ────────────────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init as _cinit
    _cinit(autoreset=True)
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN   = Fore.CYAN
    BOLD   = Style.BRIGHT
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

# ── Import keyword registry ────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from keywords import KEYWORD_REGISTRY

DEFAULT_CSV    = os.path.join(HERE, "test_suite.csv")
DEFAULT_REPORT = os.path.join(HERE, "..", "reports", "kdt_report.txt")


# ═══════════════════════════════════════════════════════════════════════════════

def _banner(text: str, width: int = 70, char: str = "═") -> str:
    return f"\n{char * width}\n  {text}\n{char * width}"


def run_suite(csv_path: str) -> list[dict]:
    """Execute every row in the CSV and return result records."""
    results = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            test_id   = row.get("test_id", "?").strip()
            desc      = row.get("description", "").strip()
            keyword   = row.get("keyword", "").strip().upper()
            args      = [row.get(f"arg{i}", "").strip() for i in range(1, 4)]
            args      = [a for a in args if a]   # drop empty trailing args
            expected  = row.get("expected_result", "PASS").strip().upper()

            if not keyword:
                continue   # skip blank rows

            fn = KEYWORD_REGISTRY.get(keyword)
            if fn is None:
                result = {
                    "test_id": test_id,
                    "description": desc,
                    "keyword": keyword,
                    "args": args,
                    "status": "ERROR",
                    "detail": f"Unknown keyword: '{keyword}'",
                    "expected": expected,
                }
                results.append(result)
                continue

            try:
                passed, detail = fn(*args)
                actual = "PASS" if passed else "FAIL"
                status = actual if actual == expected else "UNEXPECTED"
                # If expected is PASS and we got PASS → PASS
                # If expected is FAIL and we got FAIL → PASS (negative test)
                if expected == "FAIL" and actual == "FAIL":
                    status = "PASS"
                elif expected == "PASS" and actual == "PASS":
                    status = "PASS"
                else:
                    status = "FAIL"
            except Exception as exc:
                detail = f"Exception: {exc}"
                status = "ERROR"

            results.append({
                "test_id":     test_id,
                "description": desc,
                "keyword":     keyword,
                "args":        args,
                "status":      status,
                "detail":      detail,
                "expected":    expected,
            })

    return results


def print_report(results: list[dict]) -> None:
    """Pretty-print results to stdout."""
    print(_banner("BTMS — Keyword-Driven Test Report", char="═"))
    print(f"  Run at : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Total  : {len(results)} test cases\n")

    col_id   = 14
    col_kw   = 45
    col_st   = 8

    header = (
        f"{'Test ID':<{col_id}} "
        f"{'Description / Keyword':<{col_kw}} "
        f"{'Status':<{col_st}} "
        f"Detail"
    )
    print(f"{BOLD}{header}{RESET}")
    print("─" * 110)

    for r in results:
        st = r["status"]
        if st == "PASS":
            colour, icon = GREEN,  "✓"
        elif st == "FAIL":
            colour, icon = RED,    "✗"
        else:
            colour, icon = YELLOW, "!"

        desc_line = r["description"][:col_kw - 2] if len(r["description"]) > col_kw else r["description"]
        line = (
            f"{r['test_id']:<{col_id}} "
            f"{desc_line:<{col_kw}} "
            f"{colour}{icon} {st:<{col_st - 2}}{RESET} "
            f"{r['detail']}"
        )
        print(line)

    # ── Summary ────────────────────────────────────────────────────────────────
    passed  = sum(1 for r in results if r["status"] == "PASS")
    failed  = sum(1 for r in results if r["status"] == "FAIL")
    errors  = sum(1 for r in results if r["status"] == "ERROR")
    total   = len(results)
    pct     = (passed / total * 100) if total else 0

    print("─" * 110)
    print(f"\n{BOLD}Summary:{RESET}")
    print(f"  {GREEN}Passed : {passed}{RESET}")
    print(f"  {RED}Failed : {failed}{RESET}")
    print(f"  {YELLOW}Errors : {errors}{RESET}")
    print(f"  Pass rate: {pct:.1f}%\n")


def save_report(results: list[dict], path: str) -> None:
    """Write a plain-text summary to a file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "BTMS Keyword-Driven Test Report",
        f"Run at: {datetime.datetime.now().isoformat()}",
        "",
        f"{'Test ID':<14} {'Description':<45} {'Status':<8} Detail",
        "-" * 110,
    ]
    for r in results:
        lines.append(
            f"{r['test_id']:<14} {r['description'][:44]:<45} {r['status']:<8} {r['detail']}"
        )
    passed = sum(1 for r in results if r["status"] == "PASS")
    total  = len(results)
    lines += ["", f"Passed {passed}/{total}  ({passed/total*100:.1f}%)"]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Report saved → {path}")


# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="BTMS Keyword-Driven Test Runner")
    parser.add_argument("--csv",    default=DEFAULT_CSV,    help="Path to test suite CSV")
    parser.add_argument("--report", default=None,           help="Path to save plain-text report")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[ERROR] CSV not found: {args.csv}")
        sys.exit(1)

    results = run_suite(args.csv)
    print_report(results)

    report_path = args.report or DEFAULT_REPORT
    save_report(results, report_path)

    failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
