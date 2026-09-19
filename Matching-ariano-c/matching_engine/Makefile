CC      ?= cc
STD     := -std=c17
WARN    := -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes
INC     := -Iinclude
LIB_SRC := src/alloc.c src/domain.c src/matcher.c src/batch.c src/report.c

.PHONY: all test valgrind clean

all: build/ariano_demo

build:
	mkdir -p build

build/ariano_demo: $(LIB_SRC) src/main.c | build
	$(CC) $(STD) $(WARN) -O2 $(INC) $^ -o $@ -lm

build/run_tests: $(LIB_SRC) tests/test_matcher.c | build
	$(CC) $(STD) $(WARN) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -DARIANO_TESTING $(INC) $^ -o $@ -lm

test: build/run_tests
	./build/run_tests

build/run_tests_plain: $(LIB_SRC) tests/test_matcher.c | build
	$(CC) $(STD) $(WARN) -O0 -g -DARIANO_TESTING $(INC) $^ -o $@ -lm

valgrind: build/run_tests_plain
	valgrind --leak-check=full --error-exitcode=1 ./build/run_tests_plain

clean:
	rm -rf build
