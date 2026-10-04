#!/bin/sh
# jq is Serverless Workflow's default expression language. Run: sh jq-checks.sh (needs jq; 1.7 here).
set -e
echo "missing field:      $(echo '{}' | jq -c '.payout > 1000')"
echo "as a conditional:   $(echo '{}' | jq -c 'if .payout > 1000 then "approval needed" else "no approval" end')"
echo "clock:              $(jq -n 'now | type')"
echo "environment:        $(jq -n '$ENV | has("HOME")')"
