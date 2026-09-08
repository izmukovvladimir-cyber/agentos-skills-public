#!/bin/bash
set -euo pipefail

# Setup gws credentials on a remote server via Tailscale
# Usage: bash setup-remote.sh <server-ip-or-hostname>
# Example: bash setup-remote.sh YOUR_SERVER_IP

SERVER="${1:?Usage: setup-remote.sh <server-ip>}"
GWS_CONFIG="$HOME/.config/gws"

echo "[1/5] Checking local gws config..."
for f in client_secret.json credentials.json token_cache.json; do
    if [ ! -f "$GWS_CONFIG/$f" ]; then
        echo "ERROR: $GWS_CONFIG/$f not found"
        exit 1
    fi
done
echo "  OK: all 3 files present"

echo "[2/5] Creating remote directory..."
ssh "$SERVER" "mkdir -p ~/.config/gws" 2>&1
echo "  OK"

echo "[3/5] Copying credentials..."
scp "$GWS_CONFIG/client_secret.json" "$SERVER:~/.config/gws/"
scp "$GWS_CONFIG/credentials.json" "$SERVER:~/.config/gws/"
scp "$GWS_CONFIG/token_cache.json" "$SERVER:~/.config/gws/"
echo "  OK: 3 files copied"

echo "[4/5] Setting permissions..."
ssh "$SERVER" "chmod 600 ~/.config/gws/credentials.json ~/.config/gws/token_cache.json"
echo "  OK: chmod 600"

echo "[5/5] Testing access..."
RESULT=$(ssh "$SERVER" "gws auth status 2>/dev/null" 2>&1 || echo '{"error":"gws not installed"}')
echo "$RESULT" | python3 -c "
import json, sys
try:
    s = json.load(sys.stdin)
    if 'error' in s:
        print(f'  WARN: {s[\"error\"]}')
        print('  Install gws on remote: pip install google-workspace-cli')
    else:
        valid = s.get('token_valid', False)
        user = s.get('user', '?')
        print(f'  User: {user}')
        print(f'  Token valid: {valid}')
        if valid:
            print('  PASS: gws ready on {server}')
        else:
            print('  Token expired but will auto-refresh on first call')
except:
    print('  WARN: could not parse gws output, check manually')
"

echo ""
echo "Done. Test with: ssh $SERVER \"gws gmail users messages list --params '{\\\"userId\\\":\\\"me\\\",\\\"maxResults\\\":1}'\""
