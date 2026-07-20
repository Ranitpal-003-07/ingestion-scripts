#!/usr/bin/env python3
"""
seeker_search_bench.py — load/timing benchmark for seeker -> lake search calls.

Purpose
-------
Seeker's search endpoints (which forward to the lake `_search` / `_search_new`
endpoint) can be made to run *serially* via a semaphore gate
(LAKE_SEARCH_MAX_CONCURRENCY=1) or in *parallel* (LAKE_SEARCH_MAX_CONCURRENCY=0).
This script fires a fixed number of search requests at a chosen concurrency,
checks each one works, and reports timing so you can compare the two builds and
decide whether serialization made things slower / faster / the same.

It uses only the Python standard library (no `pip install`).

Typical workflow
-----------------
1) Run seeker with the SERIAL gate:   LAKE_SEARCH_MAX_CONCURRENCY=1
       python3 seeker_search_bench.py run \
           --url http://localhost:8080 --dataset my_logs \
           --auth "Basic <base64>" \
           --requests 300 --concurrency 30 --randomize \
           --label serial --out serial.json

2) Restart seeker with the PARALLEL gate (kill-switch): LAKE_SEARCH_MAX_CONCURRENCY=0
       python3 seeker_search_bench.py run \
           --url http://localhost:8080 --dataset my_logs \
           --auth "Basic <base64>" \
           --requests 300 --concurrency 30 --randomize \
           --label parallel --out parallel.json

3) Compare:
       python3 seeker_search_bench.py compare serial.json parallel.json

Run the SAME --requests/--concurrency for both so the comparison is fair.

Endpoints (profiles)
--------------------
  logs : POST {url}/datasets/{dataset}/logs   (-> QueryLogLake -> _search)
  sql  : POST {url}/api/v1/sql                 (-> QueryLogLakeSQLQuery -> _search)
  custom: any --path + --body-file with {{FROM}} {{TO}} {{DATASET}} {{LIMIT}}
          placeholders (use this to benchmark /histogram, /spans, etc.)
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict


# --------------------------------------------------------------------------- #
# Request building
# --------------------------------------------------------------------------- #
DEFAULT_SQL = (
    'SELECT "pod_name" AS key, COUNT(*) AS count '
    'FROM "fargate_poc_03" GROUP BY key ORDER BY count DESC LIMIT 20;'
)


def pick_time_window(args) -> tuple[int, int]:
    """Return (from, to) in unix seconds. Randomized windows avoid lake caching
    so repeated runs actually exercise the query path."""
    to = args.to
    lookback = args.lookback_minutes * 60
    if args.randomize:
        # window length 5 min .. lookback, ending at a random point before `to`
        window = random.randint(5 * 60, lookback)
        shift = random.randint(0, lookback)
        to = to - shift
        frm = to - window
    else:
        frm = to - lookback
    return frm, to


def build_request(args, rng_limit: int) -> tuple[str, dict, bytes]:
    """Return (url, headers, body_bytes) for one request based on the profile."""
    frm, to = pick_time_window(args)
    headers = {"Content-Type": "application/json"}
    if args.auth:
        headers["Authorization"] = args.auth
    if args.cookie:
        headers["Cookie"] = args.cookie
    for h in args.header or []:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()

    dataset = random.choice(args.dataset)

    if args.profile == "logs":
        url = f"{args.url}/datasets/{dataset}/logs"
        body = {
            "streamName": dataset,
            "limit": rng_limit,
            "offSet": 0,
            "from": frm,
            "to": to,
            "filterGroups": [],
            # seeker always emits ORDER BY for this endpoint, so orderBy.name must
            # be a real column or lake rejects the query ("No field named desc").
            # _timestamp exists on every dataset.
            "orderBy": {"name": args.order_by, "dataType": ""},
            "orderByDirection": "desc",
            "routing": 0,
        }
        return url, headers, json.dumps(body).encode()

    if args.profile == "sql":
        url = f"{args.url}/api/v1/sql"
        query = args.sql
        body = {
            "limit": rng_limit,
            "offSet": 0,
            "from": frm,
            "to": to,
            "query": query,
            "routing": 0,
            "streamType": args.stream_type,
        }
        return url, headers, json.dumps(body).encode()

    # custom profile: template file with placeholders
    url = f"{args.url}{args.path}"
    template = args.body_template
    rendered = (
        template.replace("{{FROM}}", str(frm))
        .replace("{{TO}}", str(to))
        .replace("{{DATASET}}", dataset)
        .replace("{{LIMIT}}", str(rng_limit))
    )
    return url, headers, rendered.encode()


# --------------------------------------------------------------------------- #
# Single request execution
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    latency_ms: float
    status: int
    ok: bool
    bytes: int = 0
    hits: int | None = None
    error: str = ""


def do_request(args, rng_limit: int) -> Result:
    url, headers, body = build_request(args, rng_limit)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read()
            latency = (time.perf_counter() - t0) * 1000.0
            hits = _extract_hits(raw)
            return Result(latency, resp.status, 200 <= resp.status < 300, len(raw), hits)
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - t0) * 1000.0
        detail = ""
        try:
            detail = e.read()[:200].decode("utf-8", "replace")
        except Exception:
            pass
        return Result(latency, e.code, False, error=f"HTTP {e.code}: {detail}")
    except Exception as e:  # timeout, connection refused, etc.
        latency = (time.perf_counter() - t0) * 1000.0
        return Result(latency, 0, False, error=f"{type(e).__name__}: {e}")


def _extract_hits(raw: bytes) -> int | None:
    """Best-effort correctness signal: how many rows came back."""
    try:
        data = json.loads(raw)
    except Exception:
        return None
    for key in ("matches", "hits", "data"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, list):
            return len(v)
    if isinstance(data, dict) and isinstance(data.get("total"), (int, float)):
        return int(data["total"])
    return None


# --------------------------------------------------------------------------- #
# Benchmark driver
# --------------------------------------------------------------------------- #
@dataclass
class Summary:
    label: str
    profile: str
    requests: int
    concurrency: int
    wall_seconds: float
    throughput_rps: float
    ok: int
    failed: int
    success_rate: float
    latency_ms: dict = field(default_factory=dict)
    status_codes: dict = field(default_factory=dict)
    errors_sample: list = field(default_factory=list)
    total_hits: int = 0


def percentiles(values: list[float]) -> dict:
    if not values:
        return {}
    s = sorted(values)

    def p(q: float) -> float:
        if len(s) == 1:
            return s[0]
        idx = q / 100.0 * (len(s) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(s) - 1)
        frac = idx - lo
        return s[lo] * (1 - frac) + s[hi] * frac

    return {
        "min": round(s[0], 1),
        "p50": round(p(50), 1),
        "p90": round(p(90), 1),
        "p95": round(p(95), 1),
        "p99": round(p(99), 1),
        "max": round(s[-1], 1),
        "mean": round(statistics.fmean(s), 1),
    }


def run_bench(args) -> Summary:
    # Warmup (not measured) — primes connections / caches.
    for _ in range(args.warmup):
        do_request(args, random.choice(args.limits))

    results: list[Result] = []
    print(
        f"[run] label={args.label!r} profile={args.profile} "
        f"requests={args.requests} concurrency={args.concurrency} ...",
        file=sys.stderr,
    )
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [
            ex.submit(do_request, args, random.choice(args.limits))
            for _ in range(args.requests)
        ]
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % max(1, args.requests // 10) == 0:
                print(f"    {done}/{args.requests} done", file=sys.stderr)
    wall = time.perf_counter() - t_start

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    status_codes: dict[str, int] = {}
    for r in results:
        status_codes[str(r.status)] = status_codes.get(str(r.status), 0) + 1

    summary = Summary(
        label=args.label,
        profile=args.profile,
        requests=args.requests,
        concurrency=args.concurrency,
        wall_seconds=round(wall, 3),
        throughput_rps=round(len(results) / wall, 2) if wall > 0 else 0.0,
        ok=len(ok),
        failed=len(failed),
        success_rate=round(100.0 * len(ok) / len(results), 2) if results else 0.0,
        latency_ms=percentiles([r.latency_ms for r in results]),
        status_codes=status_codes,
        errors_sample=[r.error for r in failed[:5]],
        total_hits=sum(r.hits or 0 for r in ok),
    )
    return summary


def print_summary(s: Summary) -> None:
    lat = s.latency_ms or {}
    print("\n" + "=" * 60)
    print(f" RESULT: {s.label}  (profile={s.profile})")
    print("=" * 60)
    print(f" requests        : {s.requests}  @ concurrency {s.concurrency}")
    print(f" wall time       : {s.wall_seconds:.3f} s")
    print(f" throughput      : {s.throughput_rps:.2f} req/s")
    print(f" success         : {s.ok}/{s.requests}  ({s.success_rate:.1f}%)")
    print(f" status codes    : {s.status_codes}")
    print(f" total hits seen : {s.total_hits}")
    if lat:
        print(
            f" latency ms      : min={lat['min']} p50={lat['p50']} "
            f"p90={lat['p90']} p95={lat['p95']} p99={lat['p99']} "
            f"max={lat['max']} mean={lat['mean']}"
        )
    if s.errors_sample:
        print(" error samples   :")
        for e in s.errors_sample:
            print(f"   - {e}")
    print("=" * 60)
    if s.failed:
        print(f" WARNING: {s.failed} request(s) failed — check seeker is up, "
              f"the dataset exists, and auth/headers are correct.")
    print()


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
def cmd_compare(path_a: str, path_b: str) -> None:
    with open(path_a) as f:
        a = json.load(f)
    with open(path_b) as f:
        b = json.load(f)

    def g(d, *keys, default=0):
        for k in keys:
            d = d.get(k, {}) if isinstance(d, dict) else {}
        return d if d != {} else default

    la, lb = a.get("label", "A"), b.get("label", "B")
    print("\n" + "=" * 72)
    print(f" COMPARE   {la}  vs  {lb}")
    print("=" * 72)
    if a.get("requests") != b.get("requests") or a.get("concurrency") != b.get("concurrency"):
        print(" NOTE: runs used different requests/concurrency — comparison is not "
              "apples-to-apples.")
    rows = [
        ("wall time (s)", a["wall_seconds"], b["wall_seconds"], "lower"),
        ("throughput (req/s)", a["throughput_rps"], b["throughput_rps"], "higher"),
        ("success rate (%)", a["success_rate"], b["success_rate"], "higher"),
        ("latency p50 (ms)", g(a, "latency_ms", "p50"), g(b, "latency_ms", "p50"), "lower"),
        ("latency p95 (ms)", g(a, "latency_ms", "p95"), g(b, "latency_ms", "p95"), "lower"),
        ("latency p99 (ms)", g(a, "latency_ms", "p99"), g(b, "latency_ms", "p99"), "lower"),
        ("latency max (ms)", g(a, "latency_ms", "max"), g(b, "latency_ms", "max"), "lower"),
    ]
    print(f" {'metric':<22}{la:>16}{lb:>16}{'delta':>16}")
    print(" " + "-" * 70)
    for name, va, vb, better in rows:
        if va in (0, None):
            delta = "n/a"
        else:
            pct = (vb - va) / va * 100.0
            delta = f"{pct:+.1f}%"
        print(f" {name:<22}{va:>16}{vb:>16}{delta:>16}")
    print(" " + "-" * 70)

    # Verdict based on throughput (within +/-5% == same).
    ta, tb = a["throughput_rps"], b["throughput_rps"]
    if ta > 0:
        pct = (tb - ta) / ta * 100.0
        if abs(pct) <= 5:
            verdict = f"SAME (throughput within {pct:+.1f}%)"
        elif pct > 5:
            verdict = f"{lb} is FASTER (+{pct:.1f}% throughput vs {la})"
        else:
            verdict = f"{lb} is SLOWER ({pct:.1f}% throughput vs {la})"
        print(f" VERDICT: {verdict}")
    print("=" * 72 + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a benchmark", formatter_class=argparse.RawDescriptionHelpFormatter)
    r.add_argument("--url", required=True, help="seeker base URL, e.g. http://localhost:8080")
    r.add_argument("--dataset", action="append", default=["fargate_poc_03"],
                   help="dataset/stream name (repeat to spread load across datasets)")
    r.add_argument("--profile", choices=["logs", "sql", "custom"], default="sql")
    r.add_argument("--requests", type=int, default=200, help="total number of requests")
    r.add_argument("--concurrency", type=int, default=20, help="parallel workers")
    r.add_argument("--timeout", type=float, default=120.0, help="per-request timeout (s)")
    r.add_argument("--warmup", type=int, default=3, help="unmeasured warmup requests")
    r.add_argument("--randomize", action="store_true",
                   help="randomize time windows/limits to avoid lake caching")
    r.add_argument("--to", type=int, default=1778755404,
                   help="end of query window (unix seconds)")
    r.add_argument("--lookback-minutes", type=int, default=40,
                   help="minutes before --to for the start of the query window")
    r.add_argument("--limits", type=int, nargs="+", default=[100],
                   help="candidate result limits (one picked per request)")
    r.add_argument("--auth", help='Authorization header value, e.g. "Basic <b64>" or "Bearer <jwt>"')
    r.add_argument("--cookie", help="Cookie header value")
    r.add_argument("--header", action="append", help='extra header "Key: Value" (repeatable)')
    r.add_argument("--order-by", default="_timestamp",
                   help="column to sort by (must exist on the dataset; default _timestamp)")
    r.add_argument("--sql", default=DEFAULT_SQL, help="SQL for --profile sql")
    r.add_argument("--stream-type", default="logs", help="streamType for --profile sql")
    r.add_argument("--path", help="custom request path for --profile custom (begins with /)")
    r.add_argument("--body-file", help="JSON body template file for --profile custom "
                                        "(supports {{FROM}} {{TO}} {{DATASET}} {{LIMIT}})")
    r.add_argument("--label", default="run", help="label for this run (e.g. serial / parallel)")
    r.add_argument("--out", help="write summary JSON to this path")

    c = sub.add_parser("compare", help="compare two run JSON files")
    c.add_argument("file_a")
    c.add_argument("file_b")
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.cmd == "compare":
        cmd_compare(args.file_a, args.file_b)
        return 0

    # validate custom profile
    args.body_template = ""
    if args.profile == "custom":
        if not args.path or not args.body_file:
            print("ERROR: --profile custom requires --path and --body-file", file=sys.stderr)
            return 2
        with open(args.body_file) as f:
            args.body_template = f.read()

    summary = run_bench(args)
    print_summary(summary)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(asdict(summary), f, indent=2)
        print(f"[saved] {args.out}", file=sys.stderr)

    # Non-zero exit if anything failed, so CI/automation can catch a broken run.
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
