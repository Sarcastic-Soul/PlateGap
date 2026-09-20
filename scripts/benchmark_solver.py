"""Time the four solver actions, so sizing decisions rest on numbers.

Not part of the deployment. It exists because two questions kept being
answered by guesswork: how much Lambda memory the function should have, and
whether arm64 is really faster than x86_64 for this solver. Both are
answerable by running the thing, and neither is answerable by reasoning about
it, so this script runs the thing.

It drives `lambda/handler.py` rather than calling `solver/` directly, which
means it measures the same code path a request takes -- menu resolution,
profile defaulting and input cleaning included -- just without the network and
without the Lambda CPU share. The absolute numbers are therefore a floor: a
Lambda at less than a whole vCPU will be slower by roughly the reciprocal of
its share.

    uv run python scripts/benchmark_solver.py
    uv run python scripts/benchmark_solver.py --repeat 15 --json results.json

To settle an architecture question, run it on both machines with the same
--repeat and compare the medians. The header it prints records the machine, so
a pasted result carries its own provenance.

One caveat worth knowing before comparing two numbers: on a hybrid CPU the
scheduler will move this between performance and efficiency cores, and on a
12th-gen i5 that alone was the difference between a 696 ms audit and a 1220 ms
one -- larger than most of the effects anyone would run this to detect. Pin it
to a single core for anything you intend to compare:

    taskset -c 0 uv run python scripts/benchmark_solver.py

and to model a Lambda's fractional vCPU, cap that core:

    systemd-run --user --scope -p CPUQuota=29% -q \
        taskset -c 0 uv run python scripts/benchmark_solver.py
"""

import argparse
import gc
import json
import os
import platform
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambda"))

# Importing the handler is itself work -- it reads and parses the food catalog
# and every menu preset -- so it is timed separately below rather than folded
# into the first measurement of whichever action happens to run first. On
# Lambda this cost lands on the cold start, not on the request.
_import_started = time.perf_counter()
import handler as lambda_handler  # noqa: E402
IMPORT_SECONDS = time.perf_counter() - _import_started


# The action names are the ones the front end posts. `solve` is the cheapest
# fix and `audit` is the whole-week menu audit; they are spelled here the way
# `solver/plan.py` and `solver/audit.py` name the functions underneath, since
# that is what a reader chasing a slow number will go looking for.
CASES = [
    ("gap", "plan.gap", {"action": "gap"}),
    ("cheapest", "plan.cheapest", {"action": "solve"}),
    ("frontier", "plan.frontier", {"action": "frontier"}),
    ("audit_week", "audit.audit_week", {"action": "audit"}),
]


def machine():
    """Everything needed to tell two runs of this script apart."""
    return {
        "arch": platform.machine(),
        "processor": platform.processor() or "unknown",
        "system": "%s %s" % (platform.system(), platform.release()),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "cpu_count": os.cpu_count(),
    }


def time_one(body):
    """One call, in seconds.

    The garbage collector is disabled across the measurement. The solver
    allocates heavily and a collection landing inside one repeat and not
    another is the largest source of spread in an otherwise quiet loop; the
    interest here is in comparing two machines, not in modelling GC.
    """
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        started = time.perf_counter()
        lambda_handler.ACTIONS[body["action"]](dict(body))
        return time.perf_counter() - started
    finally:
        if was_enabled:
            gc.enable()


def run(case, repeat, warmup, extra):
    body = dict(case[2], **extra)
    for _ in range(warmup):
        time_one(body)
    samples = [time_one(body) for _ in range(repeat)]
    return {
        "action": case[0],
        "function": case[1],
        "samples_ms": [round(s * 1000, 3) for s in samples],
        "min_ms": round(min(samples) * 1000, 2),
        "median_ms": round(statistics.median(samples) * 1000, 2),
        "max_ms": round(max(samples) * 1000, 2),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=9,
                        help="timed runs per action (default 9)")
    parser.add_argument("--warmup", type=int, default=2,
                        help="untimed runs per action first (default 2)")
    parser.add_argument("--menu", default="iiit",
                        help="menu preset id (default iiit, the live default)")
    parser.add_argument("--day", default="mon",
                        help="day for the single-day actions (default mon)")
    parser.add_argument("--json", metavar="PATH",
                        help="also write the full result, samples included")
    args = parser.parse_args(argv)

    extra = {"menuId": args.menu, "day": args.day}
    host = machine()

    print("PlateGap solver benchmark")
    print("  machine    %s, %d cores, %s" % (host["arch"], host["cpu_count"],
                                             host["system"]))
    print("  python     %s %s" % (host["implementation"], host["python"]))
    print("  menu       %s, day %s" % (args.menu, args.day))
    print("  repeats    %d timed, %d warmup" % (args.repeat, args.warmup))
    print("  catalog    %.0f ms to import and parse (a cold start, not a request)"
          % (IMPORT_SECONDS * 1000))
    print()
    print("  %-12s %10s %10s %10s" % ("action", "min ms", "median ms", "max ms"))

    results = []
    for case in CASES:
        result = run(case, args.repeat, args.warmup, extra)
        results.append(result)
        print("  %-12s %10.1f %10.1f %10.1f"
              % (result["action"], result["min_ms"], result["median_ms"],
                 result["max_ms"]))

    payload = {
        "machine": host,
        "menu": args.menu,
        "day": args.day,
        "repeat": args.repeat,
        "warmup": args.warmup,
        "import_ms": round(IMPORT_SECONDS * 1000, 2),
        "results": results,
    }

    if args.json:
        with open(args.json, "w") as out:
            json.dump(payload, out, indent=2)
            out.write("\n")
        print("\n  written to %s" % args.json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
