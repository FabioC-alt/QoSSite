package function

import (
	"fmt"
	"net/http"
)

// Handle an HTTP Request.
func Handle(w http.ResponseWriter, r *http.Request) {
	// Print "Hello, world!" to the server logs
	fmt.Println("Hello, world!")

	// Write "Hello, world!" to the HTTP response
	fmt.Fprintln(w, "Hello, world!")
}

