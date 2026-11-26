"""
Benchmarks ao vivo para a página "Desempenho": sequencial x paralelo.

Dois testes, cada um roda numa thread em segundo plano e é acompanhado pela
interface por polling (GET /bench/jobs/{id}):

* **Motor (C + pthreads)**: base sintética gerada no C; mede 1 thread e depois
  T threads, lendo o progresso de cada thread ao vivo. A base é repetida em
  "rodadas" até a versão sequencial levar ~ENGINE_TARGET_S segundos, para as
  barras ficarem visíveis em qualquer máquina.
* **Editais (processos)**: lê os mesmos PDFs um de cada vez e depois N ao mesmo
  tempo (cada leitura é um processo do scraper), registrando início e fim de
  cada um para desenhar a linha do tempo.

Só um teste roda por vez no servidor inteiro (o plano gratuito tem pouca CPU).
Os jobs ficam em memória: com um único processo (WEB_CONCURRENCY=1) isso basta.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..engine import bench as engine_bench
from . import document_service

API_DIR = Path(__file__).resolve().parents[2]
PDF_DIR = Path(os.environ.get("ARIANO_BENCH_PDF_DIR", API_DIR / "bench" / "pdfs"))
REFERENCE_FILE = API_DIR / "static" / "bench-reference.json"

ENGINE_TARGET_S = float(os.environ.get("ARIANO_BENCH_TARGET_S", "4"))
ENGINE_MAX_ROUNDS = 200
ACTOR_CHOICES = (50_000, 100_000, 200_000)
THREAD_CHOICES = (2, 4, 8)
CONCURRENCY_CHOICES = (2, 3, 4)


class Busy(Exception):
    """Já existe um teste rodando."""


_lock = threading.Lock()
_running: str | None = None
_jobs: dict[str, dict] = {}


# ------------------------------------------------------------ informações

def cpu_info() -> dict:
    """Núcleos visíveis e a cota de CPU do container (cgroup v2/v1), se houver."""
    visible = os.cpu_count() or 1
    try:
        usable = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        usable = visible
    quota = None
    try:
        raw = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if raw and raw[0] != "max":
            quota = int(raw[0]) / int(raw[1])
    except (OSError, ValueError, IndexError):
        try:
            q = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
            p = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
            quota = q / p if q > 0 else None
        except (OSError, ValueError):
            quota = None
    return {"cpu_count": visible, "usable_cpus": usable, "cpu_quota": quota}


def reference() -> dict | None:
    try:
        return json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pdf_files() -> list[Path]:
    return sorted(PDF_DIR.glob("*.pdf"))


# ------------------------------------------------------------------ jobs

def _start(kind: str, params: dict, target) -> dict:
    global _running
    with _lock:
        if _running is not None and _jobs.get(_running, {}).get("status") == "running":
            raise Busy("já existe um teste em andamento; aguarde ele terminar")
        job_id = uuid.uuid4().hex[:12]
        # Todas as chaves existem desde o início: a thread do teste só TROCA
        # valores, nunca adiciona chaves, então ler o job durante o polling é
        # seguro (um dict que muda de tamanho no meio da leitura daria erro).
        job = {"id": job_id, "kind": kind, "params": params, "status": "running",
               "phase": "preparando", "error": None, "started_at": time.time(),
               "rounds": None, "calibration_ms": None, "runs": [], "speedup": None,
               "identical": None, "tasks": [], "sequential_ms": None, "parallel_ms": None,
               "par_offset_ms": None, "_t0": None}
        _jobs[job_id] = job
        _running = job_id
        for old in sorted(_jobs, key=lambda k: _jobs[k]["started_at"])[:-6]:
            _jobs.pop(old, None)

    def runner():
        try:
            target(job)
            job["status"] = "done"
        except Exception as exc:  # o erro vai para a tela, não derruba a API
            job["status"] = "error"
            job["error"] = str(exc)
        finally:
            job["phase"] = "concluído" if job["status"] == "done" else "falhou"

    threading.Thread(target=runner, name=f"bench-{job_id}", daemon=True).start()
    return snapshot(job_id)


def snapshot(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if job is None:
        return None
    view = {k: v for k, v in job.items() if not k.startswith("_")}
    if job["kind"] == "engine":
        view["runs"] = [_engine_run_view(run) for run in job.get("runs", [])]
    if job["kind"] == "pdf":
        view["now_ms"] = (time.perf_counter() - job["_t0"]) * 1000 if job["_t0"] else 0
        view["tasks"] = [dict(task) for task in list(job["tasks"])]
    return view


# ----------------------------------------------------------------- motor

def start_engine(actors: int, threads: int) -> dict:
    return _start("engine", {"actors": actors, "threads": threads}, _run_engine)


def _engine_run_view(run: dict) -> dict:
    view = {k: v for k, v in run.items() if not k.startswith("_")}
    arr = run.get("_progress")
    if arr is not None and run["status"] == "running":
        round_done = [int(arr[t]) for t in range(len(run["chunks"]))]
        view["done"] = [run["rounds_done"] * c + d for c, d in zip(run["chunks"], round_done)]
    return view


def _run_engine(job: dict) -> None:
    actors, threads = job["params"]["actors"], job["params"]["threads"]
    job["phase"] = "gerando a base sintética"
    with engine_bench.Dataset(actors) as ds:
        # Calibração: uma rodada sequencial diz quantas rodadas cabem em ~ENGINE_TARGET_S.
        job["phase"] = "calibrando"
        probe = engine_bench.progress_array(1)
        ds.run(1, probe)            # 1ª rodada "fria" (memória ainda não tocada)
        ms, _, _ = ds.run(1, probe)  # a 2ª mede o ritmo real
        rounds = max(1, min(ENGINE_MAX_ROUNDS, round(ENGINE_TARGET_S * 1000 / max(ms, 0.001))))
        job["rounds"] = rounds
        job["calibration_ms"] = ms

        for label, t in (("Sequencial", 1), ("Paralelo", threads)):
            chunks = engine_bench.chunk_sizes(t, actors)
            run = {"label": label, "threads": len(chunks), "chunks": chunks, "rounds": rounds,
                   "rounds_done": 0, "status": "running", "done": [0] * len(chunks),
                   "total": actors * rounds, "elapsed_ms": None, "checksum": None, "passed": None,
                   "_progress": engine_bench.progress_array(t)}
            job["runs"].append(run)
            job["phase"] = f"{label.lower()} ({len(chunks)} thread{'s' if len(chunks) > 1 else ''})"
            total_ms, checksum, passed = 0.0, None, None
            for r in range(rounds):
                run["rounds_done"] = r
                ms, passed, checksum = ds.run(t, run["_progress"])
                total_ms += ms
            run.update(rounds_done=rounds, status="done", done=[c * rounds for c in chunks],
                       elapsed_ms=total_ms, checksum=f"{checksum:016x}", passed=passed,
                       _progress=None)

    seq, par = job["runs"]
    job["speedup"] = seq["elapsed_ms"] / par["elapsed_ms"] if par["elapsed_ms"] else None
    job["identical"] = seq["checksum"] == par["checksum"]


# ---------------------------------------------------------------- editais

def start_pdfs(concurrency: int) -> dict:
    files = pdf_files()
    if not files:
        raise FileNotFoundError(f"nenhum PDF de benchmark em {PDF_DIR}")
    return _start("pdf", {"concurrency": concurrency, "files": [f.name for f in files]}, _run_pdfs)


def _run_pdfs(job: dict) -> None:
    files = pdf_files()
    blobs = [(f.name, f.read_bytes()) for f in files]
    job["_t0"] = time.perf_counter()

    def read_one(mode: str, name: str, data: bytes) -> None:
        task = {"mode": mode, "file": name, "status": "running",
                "start_ms": (time.perf_counter() - job["_t0"]) * 1000, "end_ms": None,
                "competencies": None, "error": None}
        job["tasks"].append(task)
        try:
            payload = document_service.run_scraper(data, name)
            task["competencies"] = len(payload.get("competencies", []))
            task["status"] = "done"
        except Exception as exc:
            task["status"] = "error"
            task["error"] = str(exc)[:200]
        task["end_ms"] = (time.perf_counter() - job["_t0"]) * 1000

    # 1) um de cada vez
    job["phase"] = "um de cada vez"
    seq_start = (time.perf_counter() - job["_t0"]) * 1000
    for name, data in blobs:
        read_one("sequencial", name, data)
    seq_end = (time.perf_counter() - job["_t0"]) * 1000

    # 2) N ao mesmo tempo (cada leitura é um processo separado do scraper)
    n = job["params"]["concurrency"]
    job["phase"] = f"{n} ao mesmo tempo"
    par_start = (time.perf_counter() - job["_t0"]) * 1000
    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(lambda item: read_one("paralelo", *item), blobs))
    par_end = (time.perf_counter() - job["_t0"]) * 1000

    job["sequential_ms"] = seq_end - seq_start
    job["parallel_ms"] = par_end - par_start
    job["par_offset_ms"] = par_start
    job["speedup"] = job["sequential_ms"] / job["parallel_ms"] if job["parallel_ms"] else None
    if any(t["status"] == "error" for t in job["tasks"]):
        raise RuntimeError("alguma leitura de PDF falhou; veja os detalhes nas barras")
