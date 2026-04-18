#!/bin/bash
cd "$(dirname "$0")"

# Kill any leftover bridge or uvicorn processes from previous runs
pkill -f "node bridge.mjs" 2>/dev/null
pkill -f "uvicorn main:app" 2>/dev/null
sleep 1

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 -m uvicorn main:app &
UVICORN_PID=$!

sleep 2

node bridge.mjs &
BRIDGE_PID=$!

trap "kill $UVICORN_PID $BRIDGE_PID 2>/dev/null" SIGINT SIGTERM
wait
