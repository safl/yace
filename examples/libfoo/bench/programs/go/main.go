// SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
//
// SPDX-License-Identifier: GPL-2.0-only

// The benchmark through the idiomatic layer of the Go bindings, as the C one:
// by handle.PointGet() and by handle.PointVisit() with a closure.
//
// Usage: bench ROUNDS REPEAT
package main

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"foo"
)

func calls(handle *foo.Handle, rounds int) int64 {
	count := handle.PointCount()
	var sum int64
	for range rounds {
		for idx := range count {
			point, _ := handle.PointGet(idx)
			sum += int64(point.X)
		}
	}
	return sum
}

func callback(handle *foo.Handle, rounds int) int64 {
	var sum int64
	addX := func(point *foo.FooPoint) int32 {
		sum += int64(point.X)
		return 0
	}
	for range rounds {
		if _, err := handle.PointVisit(addX); err != nil {
			panic(err)
		}
	}
	return sum
}

func run(handle *foo.Handle, way string, sumOf func(*foo.Handle, int) int64, rounds, repeat int) {
	best := time.Duration(1<<63 - 1)
	var sum int64
	for range repeat {
		start := time.Now()
		sum = sumOf(handle, rounds)
		best = min(best, time.Since(start))
	}
	ns := float64(best.Nanoseconds()) / float64(rounds*int(handle.PointCount()))
	fmt.Printf("{\"target\": \"go\", \"way\": \"%s\", \"ns\": %.3f, \"sum\": %d}\n", way, ns, sum)
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: bench ROUNDS REPEAT")
		os.Exit(1)
	}
	rounds, err := strconv.Atoi(os.Args[1])
	if err != nil {
		panic(err)
	}
	repeat, err := strconv.Atoi(os.Args[2])
	if err != nil {
		panic(err)
	}

	handle, err := foo.Open("bench")
	if err != nil {
		panic(err)
	}
	defer handle.Close()
	points := make([]foo.FooPoint, foo.FOO_POINTS_MAX)
	for idx := range points {
		points[idx] = foo.FooPoint{X: int32(idx), Y: -int32(idx)}
	}
	if _, err := handle.PointAddMany(points); err != nil {
		panic(err)
	}

	run(handle, "calls", calls, rounds, repeat)
	run(handle, "callback", callback, rounds, repeat)
}
