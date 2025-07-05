#!/bin/sh
# pingcheck.sh - ping 192.168.2.20 up to 60s, mark-good via rauc on success, else reboot

IP="192.168.2.20"
TIMEOUT=60
COUNTER=0

printf "[pingcheck] Checking connectivity to %s...\n" "$IP"

while [ "$COUNTER" -lt "$TIMEOUT" ]; do
    if ping -c1 -w1 "$IP" >/dev/null 2>&1; then
        echo "[pingcheck] Ping succeeded. Marking system good with rauc."
        if command -v rauc >/dev/null 2>&1; then
            rauc status mark-good || echo "[pingcheck] Failed to mark-good via rauc"
        fi
        exit 0
    fi
    COUNTER=$((COUNTER+1))
    sleep 1
done

echo "[pingcheck] Unable to reach $IP after $TIMEOUT seconds. Rebooting..."
/sbin/reboot -f || reboot
