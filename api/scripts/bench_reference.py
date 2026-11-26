"""
Mede os mesmos testes da página Desempenho e grava static/bench-reference.json,
mostrado no site como "Referência: medido num computador da equipe".

Rode dentro da imagem Docker (precisa da libariano.so e do scraper):

    docker run --rm -v "<repo>/api/static:/out" ariano-api \
        python -m scripts.bench_reference --out /out/bench-reference.json \
        --description "Notebook do Jefferson (Docker Desktop)"
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from ariano_api.services import bench_service


def wait(job: dict) -> dict:
    while True:
        snap = bench_service.snapshot(job["id"])
        if snap["status"] != "running":
            return snap
        time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--description", default="Computador local (Docker)")
    parser.add_argument("--actors", type=int, default=200_000)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    engine = wait(bench_service.start_engine(args.actors, args.threads))
    if engine["status"] != "done":
        raise SystemExit(f"teste do motor falhou: {engine['error']}")
    print(f"motor: {engine['speedup']:.2f}x  idêntico={engine['identical']}")

    pdf = wait(bench_service.start_pdfs(args.concurrency))
    if pdf["status"] != "done":
        raise SystemExit(f"teste dos editais falhou: {pdf['error']}")
    print(f"editais: {pdf['speedup']:.2f}x")

    info = bench_service.cpu_info()
    data = {
        "machine": {"description": args.description, "cpus": info["usable_cpus"], "cpu_quota": info["cpu_quota"]},
        "measured_at": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "engine": engine,
        "pdf": pdf,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"gravado em {args.out}")


if __name__ == "__main__":
    os.environ.setdefault("ARIANO_AUTO_MIGRATE", "false")
    main()
