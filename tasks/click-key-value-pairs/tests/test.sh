#!/bin/bash
# Runs in a fresh verifier container (separate mode). Offline: no network or credentials.
# The agent's changes arrive as /logs/artifacts/agent.patch (written by [[verifier.collect]]).
cd /app/repo
mkdir -p /logs/verifier
PATCH=/logs/artifacts/agent.patch
if [ -s "$PATCH" ] && ! git apply --whitespace=nowarn "$PATCH"; then
  echo "agent patch does not apply cleanly" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi
python3 /tests/grade.py --repo /app/repo --tests /tests --out /logs/verifier
