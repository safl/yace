// SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
//
// SPDX-License-Identifier: GPL-2.0-only

/**
 * The benchmark through the idiomatic layer of the C++ bindings: as the C one,
 * by handle.point_get() and by handle.point_visit() with a lambda
 *
 * Usage: bench ROUNDS REPEAT
 */
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <limits>
#include <vector>

#include <foo.hpp>

static std::int64_t
calls(foo::handle &handle, std::size_t rounds)
{
	std::size_t count = handle.point_count();
	std::int64_t sum = 0;

	for (std::size_t round = 0; round < rounds; ++round) {
		for (std::size_t idx = 0; idx < count; ++idx) {
			sum += handle.point_get(idx)->x;
		}
	}

	return sum;
}

static std::int64_t
callback(foo::handle &handle, std::size_t rounds)
{
	std::int64_t sum = 0;
	auto add_x = [&sum](const foo::point &point) {
		sum += point.x;
		return 0;
	};

	for (std::size_t round = 0; round < rounds; ++round) {
		handle.point_visit(add_x);
	}

	return sum;
}

static void
run(foo::handle &handle, const char *way,
    const std::function<std::int64_t(foo::handle &, std::size_t)> &sum_of, std::size_t rounds,
    std::size_t repeat)
{
	auto best = std::chrono::nanoseconds::max();
	std::int64_t sum = 0;

	for (std::size_t each = 0; each < repeat; ++each) {
		auto start = std::chrono::steady_clock::now();
		sum = sum_of(handle, rounds);
		auto elapsed = std::chrono::steady_clock::now() - start;
		if (elapsed < best) {
			best = std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed);
		}
	}

	std::printf("{\"target\": \"cpp\", \"way\": \"%s\", \"ns\": %.3f, \"sum\": %lld}\n", way,
		    static_cast<double>(best.count()) /
			    static_cast<double>(rounds * handle.point_count()),
		    static_cast<long long>(sum));
}

int
main(int argc, char **argv)
{
	if (argc != 3) {
		std::fprintf(stderr, "usage: %s ROUNDS REPEAT\n", argv[0]);
		return 1;
	}
	std::size_t rounds = std::strtoull(argv[1], nullptr, 10);
	std::size_t repeat = std::strtoull(argv[2], nullptr, 10);

	auto handle = foo::open("bench");
	std::vector<foo::point> points;
	for (int idx = 0; idx < FOO_POINTS_MAX; ++idx) {
		points.push_back({.x = idx, .y = -idx});
	}
	handle.point_add_many(points);

	run(handle, "calls", calls, rounds, repeat);
	run(handle, "callback", callback, rounds, repeat);

	return 0;
}
