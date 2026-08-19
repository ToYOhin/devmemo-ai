package main

import (
	"fmt"
	"net"
	"net/url"
	"os/exec"
	"runtime"
	"strconv"

	"github.com/usememos/memos/internal/profile"
)

var runBrowserCommand = func(name string, args ...string) error {
	return exec.Command(name, args...).Start()
}

func profileAccessURL(instanceProfile *profile.Profile) string {
	host := instanceProfile.Addr
	if host == "" || host == "0.0.0.0" || host == "::" {
		host = "localhost"
	}

	return (&url.URL{
		Scheme: "http",
		Host:   net.JoinHostPort(host, strconv.Itoa(instanceProfile.Port)),
	}).String()
}

func openBrowser(targetURL string) error {
	switch runtime.GOOS {
	case "windows":
		return runBrowserCommand("rundll32", "url.dll,FileProtocolHandler", targetURL)
	case "darwin":
		return runBrowserCommand("open", targetURL)
	case "linux":
		return runBrowserCommand("xdg-open", targetURL)
	default:
		return fmt.Errorf("opening a browser is not supported on %s", runtime.GOOS)
	}
}
