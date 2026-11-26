# Paralelismo no ARIANO

Material para a disciplina de **Tópicos Avançados em Ciência da Computação**:
onde o ARIANO executa trabalho em paralelo, como isso foi implementado e como
comparar o tempo sequencial com o paralelo, ao vivo, na página **Desempenho**
do sistema.

## Resumo

| Onde | Tipo de paralelismo | Como |
|---|---|---|
| Motor de matching (C) | **Threads** (memória compartilhada) | `batch_match_parallel()` divide os atores entre N `pthreads` |
| Leitura de editais (scraper) | **Processos** (memória separada) | Cada PDF é lido por um processo próprio do scraper; até N ao mesmo tempo |
| API | Concorrência de requisições | FastAPI atende rotas num pool de threads; `ctypes` libera o GIL durante o C |

## 1. Motor de matching com threads

### O problema
Ranquear uma demanda é avaliar **cada ator** contra ela (`matcher_run`) e depois
ordenar. Cada avaliação é independente das outras: é um problema
*embaraçosamente paralelo*.

### A implementação (`src/parallel.c`)
1. **Divisão estática em blocos**: com T threads e n atores, a thread `t` avalia
   os atores `[t·n/T, (t+1)·n/T)`. Sem fila nem trava: cada thread escreve só na
   sua faixa do vetor de resultados, então não há disputa por memória.
2. **Trabalho local em cada thread**: além de avaliar, a própria thread descarta
   quem ficou abaixo do *threshold*, **ordena a sua faixa** e já corta no *top-k*.
3. **Junção**: a thread principal faz a *intercalação* (merge) das T listas já
   ordenadas.
4. **Progresso**: cada thread grava quantos atores já avaliou num contador
   próprio (`__atomic_store_n`, ordem relaxada), lido pela interface para
   desenhar uma barra por thread.

### Por que ordenar dentro de cada thread? (Lei de Amdahl)
A primeira versão avaliava em paralelo e **ordenava tudo no fim, numa thread só**.
Resultado medido: só **1,4×** mais rápido com 4 threads, porque a parte
sequencial (ordenar 200 mil resultados) limitava o ganho. Movendo a ordenação
para dentro das threads, a parte sequencial virou só a intercalação, e o ganho
subiu para **~3×** com 4 threads e **~3,7×** com 8.

### Mesmo resultado, sempre
A ordem do ranking é **total e determinística** (score → menos obrigatórias
faltando → menor id). Por isso o resultado paralelo é **idêntico** ao sequencial,
ator por ator. Isso é verificado de três formas:

- `tests/test_parallel.c`: compara `batch_match_parallel` com `batch_match` em
  2.728 combinações (tamanhos de 0 a 25 mil atores, 1 a 200 threads, thresholds,
  top-k, erros no meio da base, ids repetidos), sob AddressSanitizer e UBSan;
- **ThreadSanitizer** (`make test-tsan`): nenhuma condição de corrida;
- a página Desempenho mostra o *checksum* do ranking nos dois modos.

Se dois atores forem inválidos, o erro devolvido é o do de **menor índice**,
exatamente como no sequencial.

### Rodando no terminal
```bash
cd Matching-ariano-c/matching_engine
make test            # suíte original + paralelo (ASan/UBSan) + ThreadSanitizer
make bench           # tempo com 1, 2, 4 e 8 threads (200 mil atores)
make bench N=500000 REPS=5
```
> No Docker, o ThreadSanitizer precisa de `--security-opt seccomp=unconfined`
> (ele desliga a aleatorização de endereços com `setarch -R`).

## 2. Leitura de editais com processos

Ler um PDF é dominado por CPU em Python (pdfplumber). Threads Python não
paralelizam esse tipo de trabalho por causa do GIL, então o ARIANO usa
**processos**: cada leitura é um processo separado do scraper (isso já existia
para isolar PDFs problemáticos). O teste lê 4 editais um de cada vez e depois
N ao mesmo tempo, e desenha uma **linha do tempo** com início e fim de cada
leitura: no sequencial as barras formam uma escada; no paralelo, ficam lado a lado.

Os 4 editais do teste (`api/bench/pdfs/`) são trechos de 3 páginas do edital
público da Petrobras que já estava no repositório. O documento inteiro (63
páginas) levaria mais de 30 s, longo demais para uma demonstração.

## 3. Página Desempenho

Em **Desempenho**, qualquer usuário logado pode:

- escolher o tamanho da base (50, 100 ou 200 mil atores) e o número de threads
  (2, 4 ou 8) e ver **uma barra por thread** enchendo ao vivo;
- escolher quantos editais ler ao mesmo tempo (2, 3 ou 4) e ver a linha do tempo;
- ver o **speedup** (quantas vezes mais rápido) e se o ranking saiu idêntico.

A base sintética é repetida em "rodadas" até o sequencial levar ~4 s, para as
barras ficarem visíveis em qualquer máquina. Só um teste roda por vez no
servidor (um segundo pedido recebe 409).

### Por que há uma "Referência" na página
O plano gratuito do Render dá ao container uma **fração de 1 CPU**. Ali, várias
threads disputam o mesmo processador e o paralelo quase não ganha tempo, o que
não significa que o código esteja errado: não há núcleos livres. Por isso a
página mostra, junto, os mesmos testes medidos num computador da equipe
(`api/static/bench-reference.json`).

| Medido em 26/11/2026 (Docker Desktop, 8 CPUs) | Sequencial | Paralelo | Ganho |
|---|---|---|---|
| Motor, 200 mil atores × 9 rodadas, 8 threads | 2,27 s | 0,60 s | **3,8×** |
| 4 editais, 2 ao mesmo tempo | 6,31 s | 3,91 s | **1,6×** |

Para medir de novo no seu computador (com o Docker aberto, na raiz do repositório):

```bash
docker build -f api/Dockerfile -t ariano-api .
docker run --rm -v "$PWD/api/static:/out" ariano-api python -m scripts.bench_reference --out /out/bench-reference.json --description "Notebook de quem mediu"
```

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/bench/info` | CPUs e cota do servidor, opções e a referência |
| `POST` | `/bench/engine` | `{actors, threads}`: inicia o teste do motor |
| `POST` | `/bench/pdfs` | `{concurrency}`: inicia o teste dos editais |
| `GET` | `/bench/jobs/{id}` | Progresso (por thread / por leitura) e resultado |
