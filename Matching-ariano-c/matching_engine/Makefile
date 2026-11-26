CC      ?= cc
STD     := -std=c17
WARN    := -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes
INC     := -Iinclude
THREADS := -pthread
LIB_SRC := src/alloc.c src/domain.c src/matcher.c src/batch.c src/report.c src/parallel.c src/bench.c

ifeq ($(OS),Windows_NT)
CC := gcc
SHARED_EXT := dll
SHARED_FLAGS := -shared
else
SHARED_EXT := so
SHARED_FLAGS := -shared -fPIC
endif

.PHONY: all shared test test-matcher test-parallel test-tsan bench valgrind clean

all: build/ariano_demo

build:
	mkdir -p build

build/ariano_demo: $(LIB_SRC) src/main.c | build
	$(CC) $(STD) $(WARN) -O2 $(THREADS) $(INC) $^ -o $@ -lm

shared: build/libariano.$(SHARED_EXT)

build/libariano.$(SHARED_EXT): $(LIB_SRC) | build
	$(CC) $(STD) $(WARN) -O2 $(THREADS) $(SHARED_FLAGS) $(INC) $^ -o $@ -lm

# Suite original (sequencial), com injecao de falha de alocacao.
build/run_tests: $(LIB_SRC) tests/test_matcher.c | build
	$(CC) $(STD) $(WARN) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -DARIANO_TESTING $(THREADS) $(INC) $^ -o $@ -lm

# Paralelo == sequencial, sob ASan/UBSan e sob ThreadSanitizer (corridas de dados).
build/run_parallel_tests: $(LIB_SRC) tests/test_parallel.c | build
	$(CC) $(STD) $(WARN) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer $(THREADS) $(INC) $^ -o $@ -lm

build/run_parallel_tsan: $(LIB_SRC) tests/test_parallel.c | build
	$(CC) $(STD) $(WARN) -O1 -g -fsanitize=thread $(THREADS) $(INC) $^ -o $@ -lm

test-matcher: build/run_tests
	./build/run_tests

test-parallel: build/run_parallel_tests
	./build/run_parallel_tests

# setarch -R desliga o ASLR so para este processo: kernels recentes usam um
# layout de memoria que o ThreadSanitizer nao aceita ("unexpected memory mapping").
test-tsan: build/run_parallel_tsan
	setarch $$(uname -m) -R ./build/run_parallel_tsan

test: test-matcher test-parallel test-tsan

# Tempo com 1, 2, 4 e 8 threads:  make bench  [N=200000 REPS=3]
N    ?= 200000
REPS ?= 3
build/ariano_bench: $(LIB_SRC) src/bench_main.c | build
	$(CC) $(STD) $(WARN) -O2 $(THREADS) $(INC) $^ -o $@ -lm

bench: build/ariano_bench
	./build/ariano_bench $(N) $(REPS)

build/run_tests_plain: $(LIB_SRC) tests/test_matcher.c | build
	$(CC) $(STD) $(WARN) -O0 -g -DARIANO_TESTING $(THREADS) $(INC) $^ -o $@ -lm

valgrind: build/run_tests_plain
	valgrind --leak-check=full --error-exitcode=1 ./build/run_tests_plain

clean:
	rm -rf build
