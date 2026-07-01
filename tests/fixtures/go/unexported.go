// Go: unexported (lowercase) vs exported (uppercase)
package main

func ExportedFunc() int {
	return 42
}

func unexportedFunc() int {
	return 0
}
