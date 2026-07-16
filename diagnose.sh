#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$HOME/.config/glucose-monitor/config.json"
EMAIL=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('email',''))" 2>/dev/null)
PASS=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('password',''))" 2>/dev/null)

if [ -z "$EMAIL" ] || [ -z "$PASS" ]; then
    echo "No credentials found in $CONFIG"
    echo "Run glucose-monitor first to set them up, or edit the file manually."
    exit 1
fi

echo "Testing LibreLinkUp regions for $EMAIL..."
echo ""
"$DIR/venv/bin/python" -c "
from pylibrelinkup.api_url import APIUrl

for region in APIUrl:
    try:
        from pylibrelinkup import PyLibreLinkUp
        client = PyLibreLinkUp(email='$EMAIL', password='$PASS', api_url=region)
        client.authenticate()
        patients = client.get_patients()
        if patients:
            for p in patients:
                print(f'  ✓ {region.name:4s} -> {region.value}')
                print(f'      Patient: {p.first_name} {p.last_name} (id={p.id})')
        else:
            print(f'  ✗ {region.name:4s} -> {region.value}')
            print(f'      Login OK but no patients found')
    except Exception as e:
        err = str(e)[:60]
        print(f'  ✗ {region.name:4s} -> {region.value}')
        print(f'      {err}')
    print()
" 2>&1
