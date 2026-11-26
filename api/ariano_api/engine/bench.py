"""
Ponte ctypes para o benchmark do motor (include/bench.h e parallel.h).

A base sintética fica inteira na memória do C: o Python só pede "gere N
atores", "rode com T threads" e lê o progresso de cada thread enquanto o C
trabalha (ctypes libera o GIL durante a chamada, então outra thread do Python
consegue ler o array de progresso ao mesmo tempo).
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_double, c_int, c_size_t, c_uint64, c_void_p

from . import bindings

MAX_THREADS = 64
_configured = False


def _lib() -> ctypes.CDLL:
    global _configured
    lib = bindings.get_library()
    if not _configured:
        lib.bench_dataset_create.restype = c_void_p
        lib.bench_dataset_create.argtypes = [c_size_t, c_uint64]
        lib.bench_dataset_free.restype = None
        lib.bench_dataset_free.argtypes = [c_void_p]
        lib.bench_run.restype = c_int
        lib.bench_run.argtypes = [
            c_void_p, c_size_t, POINTER(c_size_t),
            POINTER(c_double), POINTER(c_size_t), POINTER(c_uint64),
        ]
        lib.parallel_effective_threads.restype = c_size_t
        lib.parallel_effective_threads.argtypes = [c_size_t, c_size_t]
        _configured = True
    return lib


def effective_threads(n_threads: int, actor_count: int) -> int:
    return int(_lib().parallel_effective_threads(n_threads, actor_count))


def chunk_sizes(n_threads: int, actor_count: int) -> list[int]:
    """Mesma divisão do C: a thread t avalia [t*n/T, (t+1)*n/T)."""
    t_eff = effective_threads(n_threads, actor_count)
    return [(t + 1) * actor_count // t_eff - t * actor_count // t_eff for t in range(t_eff)]


class Dataset:
    """Base sintética determinística no C. Use com `with` para liberar a memória."""

    def __init__(self, actors: int, seed: int = 2026):
        self.actors = actors
        self._ptr = _lib().bench_dataset_create(actors, seed)
        if not self._ptr:
            raise MemoryError(f"não foi possível gerar a base com {actors} atores")

    def run(self, threads: int, progress) -> tuple[float, int, int]:
        """Roda o lote; devolve (ms, atores acima do threshold, checksum do ranking)."""
        elapsed, passed, checksum = c_double(), c_size_t(), c_uint64()
        err = _lib().bench_run(
            self._ptr, threads, progress,
            ctypes.byref(elapsed), ctypes.byref(passed), ctypes.byref(checksum),
        )
        if err != bindings.MATCHER_OK:
            raise bindings.MatcherFailure(err)
        return elapsed.value, passed.value, checksum.value

    def close(self) -> None:
        if self._ptr:
            _lib().bench_dataset_free(self._ptr)
            self._ptr = None

    def __enter__(self) -> "Dataset":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def progress_array(n_threads: int):
    return (c_size_t * max(1, min(n_threads, MAX_THREADS)))()
