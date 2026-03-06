# Ollama on Windows: Host on LAN and Connect from Another Computer

Last updated: 2026-03-03

## Goal
Run Ollama on one Windows PC (host) and call it from another machine on your local network (client).

## 1) Host PC prerequisites
- Windows 10/11
- Admin rights (for firewall rule)
- Ollama installed from: https://ollama.com/download/windows
- Model downloaded (example: `llama3.1:8b`)

## 2) Install and verify Ollama on host
Open PowerShell on the host PC:

```powershell
ollama --version
ollama pull llama3.1:8b
ollama run llama3.1:8b
```

If the model responds locally, continue.

## 3) Make Ollama listen on LAN
By default, many local services only bind to localhost. Set Ollama host binding to all interfaces.

In **PowerShell (Admin)** on host:

```powershell
setx OLLAMA_HOST "0.0.0.0:11434" /M
```

Then restart Ollama app/service (or reboot) so the variable takes effect.

Quick check:

```powershell
$env:OLLAMA_HOST
```

Expected: `0.0.0.0:11434` (for new shells after restart/sign-out).

## 4) Allow inbound firewall traffic (LAN only)
In **PowerShell (Admin)**:

```powershell
New-NetFirewallRule -DisplayName "Ollama 11434 LAN" \
  -Direction Inbound \
  -Protocol TCP \
  -LocalPort 11434 \
  -Action Allow \
  -Profile Private
```

Optional tighter scope to a subnet (replace with your LAN CIDR):

```powershell
Set-NetFirewallRule -DisplayName "Ollama 11434 LAN" -RemoteAddress 192.168.1.0/24
```

## 5) Get host IP
On host:

```powershell
ipconfig
```

Find IPv4 address on your active adapter, for example `192.168.1.50`.

## 6) Test from client machine
From the other computer on same LAN:

```bash
curl http://192.168.1.50:11434/api/tags
```

If reachable, you should get JSON listing installed models.

Test generation:

```bash
curl http://192.168.1.50:11434/api/generate \
  -d '{"model":"llama3.1:8b","prompt":"Say hello in one sentence.","stream":false}'
```

## 7) OpenAI-compatible client usage (if your app expects OpenAI API)
Many tools can be pointed to Ollama directly with custom base URL.

Example settings:
- Base URL: `http://192.168.1.50:11434/v1`
- API key: any non-empty string (for clients that require one)
- Model: `llama3.1:8b`

Example curl (OpenAI-style chat completions):

```bash
curl http://192.168.1.50:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "user", "content": "Give me 3 short bullet points about LAN inference."}
    ]
  }'
```

## 8) Reliability and security checklist
- Keep both machines on the same private LAN.
- Do not port-forward 11434 on your router.
- Prefer Windows network profile `Private`, not `Public`.
- Keep model host awake (disable sleep while serving).
- If IP changes often, reserve a DHCP lease or use a local DNS name.

## 9) Troubleshooting
1. `Connection refused`
- Ollama not running, wrong bind host, or wrong port.
- Recheck `OLLAMA_HOST` and restart Ollama.

2. `Timed out`
- Firewall rule missing/wrong network profile.
- Client and host not on same subnet/VLAN.

3. `Model not found`
- Pull model on host:

```powershell
ollama pull llama3.1:8b
```

4. Slow responses
- Try smaller/quantized model.
- Reduce prompt/context length.
- Close GPU-heavy apps.

## 10) Minimal startup runbook
On host after reboot:

```powershell
ollama serve
```

On client test:

```bash
curl http://<HOST_IP>:11434/api/tags
```

If this works, your remote LAN setup is complete.
