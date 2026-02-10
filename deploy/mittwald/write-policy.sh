#!/bin/sh
# strfry write policy: only allow whitelisted pubkeys
# Reads JSON lines from stdin, outputs accept/reject to stdout

WHITELIST="/etc/strfry/allowed-pubkeys.txt"

while read -r line; do
    # Extract pubkey: find "pubkey":"<64 hex chars>"
    pubkey=$(echo "$line" | grep -o '"pubkey":"[a-f0-9]\{64\}"' | head -1 | cut -d'"' -f4)

    # Extract event ID: find "id":"<64 hex chars>" after "event"
    event_id=$(echo "$line" | grep -o '"event":{[^}]*"id":"[a-f0-9]\{64\}"' | grep -o '"id":"[a-f0-9]\{64\}"' | cut -d'"' -f4)

    # Fallback: if event_id is empty, try first 64-char hex id
    if [ -z "$event_id" ]; then
        event_id=$(echo "$line" | grep -o '"id":"[a-f0-9]\{64\}"' | head -1 | cut -d'"' -f4)
    fi

    # Check if pubkey is in whitelist (ignore comments and empty lines)
    if grep -v '^#' "$WHITELIST" | grep -v '^$' | grep -qx "$pubkey" 2>/dev/null; then
        printf '{"id":"%s","action":"accept"}\n' "$event_id"
    else
        printf '{"id":"%s","action":"reject","msg":"blocked: pubkey not whitelisted"}\n' "$event_id"
    fi
done
