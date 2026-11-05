// The check of the Go bindings of libfoo: calls the library through the
// idiomatic layer, its handle, errors and returned values, and prints what it
// got back, as YAML documents, or with argument "json" as JSON objects, each
// holding what 'expected.yaml' says. An error is printed as the negative errno
// the C function returned; what the layer does not take, a NULL where none is
// allowed or a callback of C, is called raw.
package main

/*
#include <stdint.h>
#include <stdlib.h>

extern int addX(void *arg, void *point);
*/
import "C"

import (
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"syscall"
	"unsafe"

	"foo"
)

var asJSON = false

type field struct {
	key   string
	value string // as JSON, which is also YAML
}

func num[T ~int | ~int32 | ~int64 | ~uint16 | ~uintptr](value T) string {
	return fmt.Sprint(value)
}

func quoted(text string) string {
	return `"` + text + `"`
}

func document(name string, fields []field) {
	if asJSON {
		parts := make([]string, len(fields))
		for idx, f := range fields {
			parts[idx] = quoted(f.key) + ": " + f.value
		}
		fmt.Printf("{%s: {%s}}\n", quoted(name), strings.Join(parts, ", "))
		return
	}
	fmt.Printf("---\n%s:\n", name)
	for _, f := range fields {
		fmt.Printf("  %s: %s\n", f.key, f.value)
	}
}

// record prints a record, or nil, with the printer the bindings give it
func record(name string, fpr func(w io.Writer, flags int) error) {
	flags := foo.FOO_PR_YAML
	if asJSON {
		flags = foo.FOO_PR_JSON
		fmt.Printf("{%s: ", quoted(name))
	} else {
		fmt.Println("---")
	}
	if err := fpr(os.Stdout, flags); err != nil {
		panic(err)
	}
	if asJSON {
		fmt.Println("}")
	}
}

// errno is the negative errno of err, 0 for none
func errno(err error) int64 {
	var found syscall.Errno
	if errors.As(err, &found) {
		return -int64(found)
	}
	if err != nil {
		panic(err)
	}
	return 0
}

// value is 'value', or the negative errno of err
func value[T ~int | ~uintptr](value T, err error) int64 {
	if err != nil {
		return errno(err)
	}
	return int64(value)
}

type shape interface{ Name() (string, bool) }

func names[T shape](values ...T) string {
	found := make([]string, len(values))
	for idx, v := range values {
		name, ok := v.Name()
		if !ok {
			name = "UNKNOWN"
		}
		found[idx] = quoted(name)
	}
	return "[" + strings.Join(found, ", ") + "]"
}

//export addX
func addX(arg unsafe.Pointer, point unsafe.Pointer) C.int {
	*(*int64)(arg) += int64((*foo.FooPoint)(point).X)
	return 0
}

func main() {
	asJSON = len(os.Args) > 1 && os.Args[1] == "json"

	document("defines", []field{
		{"FOO_NAME", quoted(foo.FOO_NAME)},
		{"FOO_MAGIC", num(foo.FOO_MAGIC)},
		{"FOO_VERSION_MAJOR", num(foo.FOO_VERSION_MAJOR)},
		{"FOO_VERSION_MINOR", num(foo.FOO_VERSION_MINOR)},
		{"FOO_VERSION_PATCH", num(foo.FOO_VERSION_PATCH)},
		{"FOO_POINTS_MAX", num(foo.FOO_POINTS_MAX)},
		{"FOO_DEFAULT_SHAPE_SIDES", num(foo.FOO_DEFAULT_SHAPE_SIDES)},
	})
	document("enums", []field{
		{"foo_shape", names[foo.FooShape](-1, 0, 1, 2, 3)},
		{"foo_option", names[foo.FooOption](1, 2, 3)},
	})

	points := []foo.FooPoint{{X: 1, Y: 2}, {X: 3, Y: 4}, {X: 5, Y: 6}}
	handle, err := foo.Open("points")
	if err != nil {
		panic(err)
	}
	defer handle.Close()
	var unopened *foo.FooHandle
	openWithoutName := foo.Foo_open(nil, &unopened)
	added := 0
	for idx := range points {
		if handle.Add(&points[idx]) == nil {
			added++
		}
	}
	count := handle.Count()

	var sumX, sumY int64
	visit := value(handle.Visit(func(point *foo.FooPoint) int32 {
		sumX += int64(point.X)
		sumY += int64(point.Y)
		return 0
	}))
	visited := 0
	stopped := value(handle.Visit(func(point *foo.FooPoint) int32 {
		visited++
		if visited == 2 {
			return 1
		}
		return 0
	}))
	without := foo.Foo_visit(handle.Ptr(), nil, nil)
	withX := (*int64)(C.malloc(C.size_t(unsafe.Sizeof(int64(0)))))
	defer C.free(unsafe.Pointer(withX))
	*withX = 0
	visitor := foo.FooVisitor{Visit: foo.FooVisitCb(C.addX), Arg: unsafe.Pointer(withX)}
	visitWith := value(handle.VisitWith(&visitor))
	_, err = foo.FigureFill(3)
	unknown := errno(err)
	addMany := value(handle.AddMany(points))
	countAfter := handle.Count()
	copied, err := handle.Points(make([]foo.FooPoint, 4))
	if err != nil {
		panic(err)
	}
	var copiedX int64
	for _, p := range copied {
		copiedX += int64(p.X)
	}
	var done uintptr
	submit := errno(handle.Submit(func(count uintptr) { done = count }))
	submitBusy := errno(handle.Submit(func(count uintptr) { done = 0 }))
	poke := handle.Poke()
	pokeAgain := handle.Poke()

	document("calls", []field{
		{"version", quoted(foo.Version())},
		{"open", "0"},
		{"open_without_name", num(openWithoutName)},
		{"name", quoted(handle.Name())},
		{"added", num(added)},
		{"count", num(count)},
		{"visit", num(visit)},
		{"visit_sum_x", num(sumX)},
		{"visit_sum_y", num(sumY)},
		{"visit_stopped", num(stopped)},
		{"visit_without_callback", num(without)},
		{"visit_with", num(visitWith)},
		{"visit_with_sum_x", num(*withX)},
		{"figure_of_unknown_shape", num(unknown)},
		{"add_many", num(addMany)},
		{"count_after_add_many", num(countAfter)},
		{"points_copied", num(len(copied))},
		{"points_sum_x", num(copiedX)},
		{"submit", num(submit)},
		{"submit_busy", num(submitBusy)},
		{"poke", num(poke)},
		{"done_count", num(done)},
		{"poke_again", num(pokeAgain)},
	})

	for _, idx := range []uintptr{1, 6} {
		point, ok := handle.At(idx)
		if !ok {
			record("foo_point", (*foo.FooPoint)(nil).Fpr)
			continue
		}
		record("foo_point", point.Fpr)
	}

	for handle.Add(&points[0]) == nil {
	}
	document("full", []field{
		{"count", num(handle.Count())},
		{"add", num(errno(handle.Add(&points[0])))},
		{"add_many", num(value(handle.AddMany(points[:1])))},
	})

	status := handle.StatusGet()
	record("foo_status", status.Fpr)
	document("status", []field{
		{"pending", num(status.CodePending())},
		{"points", num(status.CodePoints())},
		{"full", num(status.CodeFull())},
	})
	made := foo.FooStatus{Code: 0, Max: foo.FOO_POINTS_MAX}
	made.SetCodePoints(5)
	made.SetCodePending(1)
	record("foo_status", made.Fpr)

	scalars := foo.ScalarsFill()
	record("foo_scalars", scalars.Fpr)
	for _, shape := range []foo.FooShape{foo.FOO_SHAPE_POINT, foo.FOO_SHAPE_LINE, foo.FOO_SHAPE_POLYGON} {
		figure, err := foo.FigureFill(uint32(shape))
		if err != nil {
			panic(err)
		}
		record("foo_figure", figure.Fpr)
	}
	set := foo.ValueSet(-1)
	record("foo_value", set.Fpr)
}
