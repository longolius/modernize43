// Command modernize43 serves the transcoder web interface.
package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"

	"modernize43/internal/jobs"
	"modernize43/internal/web"
)

func main() {
	host := flag.String("host", "127.0.0.1", "bind address")
	port := flag.Int("port", 8080, "bind port")
	allowPrivate := flag.Bool("allow-private-hosts", false, "allow loopback and private source URLs")
	retention := flag.Int("retention-minutes", 60, "minutes to keep finished results")
	flag.Parse()

	manager := jobs.NewManager(*allowPrivate, *retention)
	addr := fmt.Sprintf("%s:%d", *host, *port)
	fmt.Printf("modernize43 läuft auf http://%s\n", addr)
	if err := http.ListenAndServe(addr, web.New(manager)); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
