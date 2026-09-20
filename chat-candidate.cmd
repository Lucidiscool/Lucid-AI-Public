@echo off
call "%~dp0run-directml.cmd" chat --device directml --checkpoint checkpoints/chat-curriculum/best.pt %*
pause
