#!/bin/sh
export PYTHONPATH="/workspace/releases/bin${PYTHONPATH:+:}${PYTHONPATH}"
exec /usr/bin/env python3 /workspace/releases/bin/nami.py "$@"
