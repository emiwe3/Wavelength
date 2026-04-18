#!/bin/bash
cd "$(dirname "$0")"

# Use venv if available, otherwise fall back to system python3
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 -m uvicorn main:app &
UVICORN_PID=$!

sleep 2

python3 bridge.py &
BRIDGE_PID=$!

trap "kill $UVICORN_PID $BRIDGE_PID" SIGINT SIGTERM
wait
