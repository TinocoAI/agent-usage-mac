#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/env python3 "$DIR/agent_usage.py"
