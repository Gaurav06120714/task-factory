#!/bin/bash
set -euo pipefail
cd /app/repo
git apply /solution/solution.patch
