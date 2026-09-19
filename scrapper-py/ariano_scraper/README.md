# ARIANO — Scraper/Parser de PDFs (MVP)

Pipeline local, 100% gratuito, que transforma um PDF em um JSON estruturado:

```text
PDF → validação → extração de texto → normalização → parsing (seções,
regex, competências) → validação Pydantic → JSON
```

Nenhuma dependência paga é usada. Nenhuma API de LLM (OpenAI, Claude,
Gemini) é usada nesta etapa. OCR ainda não está implementado — PDFs
sem camada de texto nativa são processados sem travar, mas com um
aviso explícito no JSON de saída (`extraction_warnings`).

## Requisitos

- Python 3.10 ou superior (desenvolvido e testado com Python 3.12).

## Instalação

```bash
python -m venv .venv
```

Ativação:

- Linux/macOS: `source .venv/bin/activate`
- Windows (cmd): `.venv\Scripts\activate.bat`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`

Instalação das dependências:

```bash
pip install -r requirements.txt
```

## Execução

```bash
python main.py ./documents/example.pdf
```

Especificando o diretório de saída:

```bash
python main.py ./documents/example.pdf --output ./output
```

Usando uma lista alternativa de competências conhecidas:

```bash
python main.py ./documents/example.pdf --known-tags ./minha_lista.json
```

Ajuda:

```bash
python main.py --help
```

O programa termina com código de saída:

- `0` — sucesso;
- `1` — erro tratado do pipeline (PDF inválido, corrompido, JSON fora do schema etc. — mensagem clara, sem traceback);
- `2` — erro inesperado.

## Estrutura do projeto

```text
ariano_scraper/
│
├── main.py                    # CLI: orquestra o pipeline completo
│
├── pdf/
│   ├── downloader.py           # download HTTP de PDFs (reservado para a etapa de scraping remoto; não usado pela CLI local)
│   ├── validator.py            # valida arquivo/assinatura/abertura/páginas/texto nativo vs OCR_REQUIRED
│   ├── extractor.py            # extrai texto por página (preserva numeração 1-based) + metadados (título)
│   └── normalizer.py           # normalização segura (Unicode, espaços, hifenização, etc.)
│
├── parser/
│   ├── document_parser.py      # detecção de seções, regex (datas/valores/prazo/organização/título), competências
│   └── known_tags.json         # fonte local de competências conhecidas (code/name/aliases)
│
├── schemas/
│   └── document_schema.py      # modelos Pydantic do JSON final
│
├── storage/
│   └── json_writer.py          # grava o JSON validado em disco (UTF-8, sem \uXXXX)
│
├── utils/
│   ├── hashing.py               # SHA-256 do arquivo
│   ├── logging.py               # logging simples e centralizado
│   ├── errors.py                # exceções do pipeline, com etapa (stage) associada
│   ├── text.py                  # helper de remoção de acentos (uso interno de comparação)
│   └── version.py               # PARSER_VERSION centralizado
│
├── documents/                   # coloque aqui os PDFs de entrada
├── output/                      # JSONs gerados
├── tests/                       # suíte automatizada (pytest)
├── requirements.txt
└── README.md
```

## Exemplo de saída

```json
{
  "processing_metadata": {
    "source_url": null,
    "source_file": "documents/example.pdf",
    "document_hash": "sha256:6164d215...",
    "processed_at": "2026-09-19T04:36:51.832280Z",
    "parser_version": "1.0.0",
    "extraction_method": "native_text",
    "ocr_used": false,
    "page_count": 3
  },
  "document": {
    "title": {"value": "Edital de Fomento à Inovação 2026", "confidence": "HIGH", "source_page": 1},
    "organization": {"value": "Secretaria de Inovacao e Tecnologia do Estado", "confidence": "MEDIUM", "source_page": 1},
    "publication_date": {"value": "2026-12-15", "confidence": "MEDIUM", "source_page": 2},
    "submission_deadline": {"value": "2026-10-30", "confidence": "HIGH", "source_page": 2}
  },
  "requirements": [
    {"text": "Possuir CNPJ ativo ha pelo menos 1 ano", "confidence": "MEDIUM", "source_page": 2}
  ],
  "competencies": [
    {"code": "AI", "name": "Artificial Intelligence", "confidence": "HIGH", "source_page": 1, "matched_text": "Inteligencia Artificial"}
  ],
  "financial": {
    "budget": {"value": 1500000.0, "confidence": "HIGH", "source_page": 3},
    "currency": "BRL"
  },
  "sections": [
    {"heading": "OBJETIVO", "page": 1, "text": "..."}
  ],
  "extraction_warnings": []
}
```

## Testes

```bash
pytest
```

Rodar com mais detalhe:

```bash
pytest -v
```

Os testes usam fixtures de PDF controladas em `tests/fixtures/` (um
edital de exemplo com texto nativo, um PDF sem texto extraível para
simular um documento escaneado, um PDF corrompido e um arquivo que não
é PDF). Não é necessário nenhum PDF externo para rodar a suíte.

## Limitações conhecidas deste MVP

- **OCR não implementado.** PDFs sem camada de texto nativa (documentos
  escaneados) são identificados (`extraction_method: "ocr_required"`)
  e processados sem travar, mas o texto extraído fica vazio/parcial.
- **Nenhum LLM é usado.** Toda extração é feita por regex e detecção
  de seções. Isso é deliberado nesta etapa — funciona bem para padrões
  previsíveis (datas, valores em R$, seções com título claro), mas não
  interpreta texto livre ou ambíguo.
- **O parser não é universal.** Foi construído para o padrão comum de
  editais/documentos institucionais brasileiros (seções como OBJETIVO,
  REQUISITOS, PRAZOS etc.). Documentos com estrutura muito diferente
  podem gerar poucos ou nenhum campo estruturado — nesse caso, o JSON
  ainda é gerado, com `extraction_warnings` explicando o que não foi
  encontrado.
- **Tabelas complexas não são interpretadas.** O `pdfplumber` extrai
  texto corrido; uma tabela com layout complexo pode virar texto fora
  de ordem.
- **Competências reconhecidas são apenas as listadas em
  `parser/known_tags.json`.** Não há inferência semântica de novas
  competências não cadastradas nesta etapa.
