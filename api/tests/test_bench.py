from __future__ import annotations

import pytest
from pydantic import ValidationError

from ariano_api.models import EngineBenchIn, PdfBenchIn
from ariano_api.services import bench_service


def test_benchmark_pdfs_are_shipped():
    names = [p.name for p in bench_service.pdf_files()]
    assert names == ["edital_a.pdf", "edital_b.pdf", "edital_c.pdf", "edital_d.pdf"]


def test_bench_inputs_only_accept_offered_choices():
    assert EngineBenchIn().actors in bench_service.ACTOR_CHOICES
    assert PdfBenchIn().concurrency in bench_service.CONCURRENCY_CHOICES
    with pytest.raises(ValidationError):
        EngineBenchIn(actors=5_000_000)  # evita derrubar o servidor de memória
    with pytest.raises(ValidationError):
        EngineBenchIn(threads=64)
    with pytest.raises(ValidationError):
        PdfBenchIn(concurrency=20)


def test_unknown_job_returns_none():
    assert bench_service.snapshot("nao-existe") is None


def test_reference_file_is_valid():
    ref = bench_service.reference()
    assert ref is not None and ref["engine"]["identical"] is True
    assert ref["engine"]["speedup"] > 1 and ref["pdf"]["speedup"] > 1
