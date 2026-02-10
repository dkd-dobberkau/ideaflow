#!/bin/sh
# strfry write policy: only allow whitelisted pubkeys
# Reads JSON lines from stdin, outputs accept/reject to stdout

WHITELIST="/etc/strfry/allowed-pubkeys.txt"

while read -r line; do
    # Extract event ID from "event":{"id":"<value>"
    event_id=$(echo "$line" | sed 's/.*"event"[^{]*{[^"]*"id":"\([a-f0-9]*\)".*/\1/')

    # Extract pubkey from "pubkey":"<value>"
    pubkey=$(echo "$line" | sed 's/.*"pubkey":"\([a-f0-9]*\)".*/\1/')

    # Check if pubkey is in whitelist (ignore comments and empty lines)
    if grep -v '^#' "$WHITELIST" | grep -qx "$pubkey" 2>/dev/null; then
        printf '{"id":"%s","action":"accept"}\n' "$event_id"
    else
        printf '{"id":"%s","action":"reject","msg":"blocked: pubkey not whitelisted"}\n' "$event_id"
    fi
done
