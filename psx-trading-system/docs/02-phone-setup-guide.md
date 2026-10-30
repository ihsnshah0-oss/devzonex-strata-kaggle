# 02 — Phone Setup Guide (use the system on your mobile)

Your phone opens the **same dashboard** running on your laptop. No app to install.

## Requirements

- Laptop and phone on the **same Wi-Fi** (home/office Wi-Fi — not mobile data on one and Wi-Fi on the other).
- System running on the laptop (see installation guide, Step 4).

## Step 1 — Find your laptop's Wi-Fi address (IP)

**Windows (PowerShell):**
```powershell
ipconfig
```
Look under "Wireless LAN adapter Wi-Fi" for `IPv4 Address`, e.g. `192.168.1.5`.

**Mac:**
```bash
ipconfig getifaddr en0
```

**Linux:**
```bash
hostname -I
```
Take the first number, e.g. `192.168.1.5`.

## Step 2 — Open on your phone

In your phone's browser (Chrome/Safari), type:

```text
http://192.168.1.5:8111
```
(Replace with YOUR laptop IP. Port `:8111` is required.)

## Step 3 — Add to home screen (optional, feels like an app)

- **iPhone (Safari):** Share button → "Add to Home Screen".
- **Android (Chrome):** Menu (⋮) → "Add to Home screen".

## Tips

- The dashboard is mobile-friendly: tables scroll sideways, charts resize.
- If the page won't load: (1) same Wi-Fi? (2) server still running? (3) laptop
  firewall blocking port 8111? On Windows, allow Python through the firewall when asked.
- Your IP can change when Wi-Fi reconnects — re-check Step 1 if it suddenly stops working.
- Never expose port 8111 to the public internet. Home Wi-Fi only.
