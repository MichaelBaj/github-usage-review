#!/usr/bin/env bash
# Generate a cryptographically random admin token and print it.
# Usage: ./scripts/gen-admin-token.sh
token=$(openssl rand -base64 32 | tr -d '/+=' | head -c 40)
echo "$token"
