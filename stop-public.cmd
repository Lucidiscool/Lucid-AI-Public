@echo off
if not exist "%~dp0runs" mkdir "%~dp0runs"
type nul > "%~dp0runs\stop-public"
echo Public sharing will stop within a few seconds. Your local AI stays available.
