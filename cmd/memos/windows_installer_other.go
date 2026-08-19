//go:build !windows

package main

func maybeRunWindowsInstaller() bool {
	return false
}
