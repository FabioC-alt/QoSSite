package function

import (
	"crypto/sha256"
	"fmt"
	"math"
	"net/http"
	"net/http/httputil"
	"runtime"
	"strings"
	"sync"
	"time"
)

// Handle an HTTP Request with heavy computational load.
func Handle(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	
	// Original request dumping
	dump, err := httputil.DumpRequest(r, true)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	fmt.Println("Received request - starting heavy processing...")
	fmt.Printf("%q\n", dump)

	// 1. CPU-intensive mathematical calculations
	result := performHeavyMath()
	
	// 2. Memory allocation stress
	memoryStress := performMemoryOperations()
	
	// 3. String processing intensive operations
	stringResult := performStringOperations(string(dump))
	
	// 4. Concurrent goroutines doing work
	concurrentResult := performConcurrentWork()
	
	// 5. Cryptographic operations
	hashResult := performCryptographicWork(dump)
	
	// 6. Simulated database/IO operations (CPU bound)
	ioSimulation := simulateHeavyIO()

	elapsed := time.Since(start)
	
	// Format response with all results
	response := fmt.Sprintf(`Heavy Processing Complete!
Processing Time: %v
Math Result: %f
Memory Operations: %d allocations
String Processing: %d operations
Concurrent Work: %s
Hash: %x
IO Simulation: %s

Original Request:
%q`, 
		elapsed, result, memoryStress, stringResult, 
		concurrentResult, hashResult, ioSimulation, dump)
	
	fmt.Fprintf(w, "%s", response)
	fmt.Printf("Request processed in %v\n", elapsed)
}

// Perform CPU-intensive mathematical calculations
func performHeavyMath() float64 {
	result := 0.0
	iterations := 10000000 // 10 million iterations
	
	for i := 0; i < iterations; i++ {
		// Complex mathematical operations
		x := float64(i)
		result += math.Sin(x) * math.Cos(x) * math.Tan(x/1000.0)
		result = math.Sqrt(math.Abs(result))
		
		// Prime number checking (expensive)
		if i%1000 == 0 {
			isPrime(int64(i + 1000))
		}
	}
	
	return result
}

// Check if a number is prime (intentionally inefficient)
func isPrime(n int64) bool {
	if n < 2 {
		return false
	}
	for i := int64(2); i < n/2; i++ {
		if n%i == 0 {
			return false
		}
	}
	return true
}

// Perform memory-intensive operations
func performMemoryOperations() int {
	allocations := 0
	
	// Create and manipulate large slices
	for i := 0; i < 1000; i++ {
		// Allocate large slices
		largeSlice := make([]int, 100000)
		for j := range largeSlice {
			largeSlice[j] = j * i
		}
		allocations++
		
		// Force garbage collection work
		if i%100 == 0 {
			runtime.GC()
		}
	}
	
	// Create nested data structures
	data := make(map[string][]string)
	for i := 0; i < 10000; i++ {
		key := fmt.Sprintf("key_%d", i)
		data[key] = make([]string, 100)
		for j := 0; j < 100; j++ {
			data[key][j] = fmt.Sprintf("value_%d_%d", i, j)
		}
		allocations++
	}
	
	return allocations
}

// Perform string processing operations
func performStringOperations(input string) int {
	operations := 0
	text := input
	
	// String manipulation operations
	for i := 0; i < 10000; i++ {
		// Expensive string operations
		text = strings.Repeat(text, 2)
		text = strings.ToUpper(text)
		text = strings.ToLower(text)
		text = strings.ReplaceAll(text, "e", "E")
		operations += 4
		
		// Keep text from growing too large
		if len(text) > 100000 {
			text = text[:50000]
		}
		
		// String searching
		strings.Contains(text, "HTTP")
		strings.Count(text, "a")
		operations += 2
	}
	
	return operations
}

// Perform concurrent heavy work
func performConcurrentWork() string {
	const numGoroutines = 100
	const workPerGoroutine = 100000
	
	var wg sync.WaitGroup
	results := make(chan float64, numGoroutines)
	
	// Launch goroutines to do parallel work
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			
			result := 0.0
			for j := 0; j < workPerGoroutine; j++ {
				result += math.Sin(float64(id*workPerGoroutine + j))
			}
			results <- result
		}(i)
	}
	
	// Wait for all goroutines
	go func() {
		wg.Wait()
		close(results)
	}()
	
	// Collect results
	totalResult := 0.0
	count := 0
	for result := range results {
		totalResult += result
		count++
	}
	
	return fmt.Sprintf("Processed %d goroutines with result: %f", count, totalResult)
}

// Perform cryptographic operations
func performCryptographicWork(data []byte) []byte {
	// Multiple rounds of hashing
	hash := data
	for i := 0; i < 10000; i++ {
		h := sha256.New()
		h.Write(hash)
		h.Write([]byte(fmt.Sprintf("iteration_%d", i)))
		hash = h.Sum(nil)
	}
	return hash
}

// Simulate heavy I/O operations (CPU-bound simulation)
func simulateHeavyIO() string {
	// Simulate file operations with CPU work
	operations := []string{}
	
	for i := 0; i < 1000; i++ {
		// Simulate file read/write with string operations
		data := strings.Repeat(fmt.Sprintf("simulated_file_content_%d\n", i), 1000)
		
		// Simulate processing the
