#!/usr/bin/env bash
# Muestra la dirección .onion del buzón.
journalctl -u buzon -n 500 --no-pager | grep -oE 'https?://[a-z2-7]{56}\.onion[^ ]*' | tail -1
