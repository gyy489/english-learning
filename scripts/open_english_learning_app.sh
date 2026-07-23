#!/bin/zsh

# Opening the URL creates the first connection. launchd then starts the backend.
exec /usr/bin/open "http://127.0.0.1:8787"
