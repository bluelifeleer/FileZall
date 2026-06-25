# FileZall Agent Deployment

This guide covers the Linux Agent build, install, SSH tunnel, and health-check flow used by FileZall desktop clients.

## Build Package

From the repository root, build the Agent tarball:

```powershell
agent\build-package.ps1
```

On macOS or Linux build hosts:

```bash
bash agent/build-package.sh
```

Both scripts create `dist/filezall-agent.tar.gz`.

## Install Or Update On Linux

Copy the package to the target server and extract it under `/opt/filezall-agent`.

```bash
sudo mkdir -p /opt/filezall-agent
sudo tar -xzf /tmp/filezall-agent.tar.gz -C /opt/filezall-agent
```

Create the runtime environment file with a random token:

```bash
printf '%s\n' 'FILEZALL_AGENT_TOKEN=replace-with-random-token' | sudo tee /opt/filezall-agent/agent.env
```

Install and start the systemd service:

```bash
sudo cp /opt/filezall-agent/filezall-agent.service /etc/systemd/system/filezall-agent.service
sudo systemctl daemon-reload
sudo systemctl enable filezall-agent
sudo systemctl restart filezall-agent
systemctl is-active --quiet filezall-agent
```

The service name is `filezall-agent`.

## SSH Tunnel

The recommended access pattern is a local SSH tunnel instead of exposing the Agent port publicly:

```bash
ssh -L 127.0.0.1:8765:127.0.0.1:8765 -p 22 deploy@example.com
```

After the tunnel is open, the desktop client can use:

```text
http://127.0.0.1:8765
```

## Health Check

Verify the Agent through the tunnel:

```bash
curl -H 'Authorization: Bearer replace-with-random-token' http://127.0.0.1:8765/health
```

Expected response:

```json
{"ok": true}
```

## Troubleshooting

Check the service state:

```bash
systemctl status filezall-agent
```

Restart after changing `FILEZALL_AGENT_TOKEN`:

```bash
sudo systemctl restart filezall-agent
```

If health checks fail, confirm the token matches the desktop site profile, the SSH tunnel is still active, and the service is listening on `127.0.0.1:8765`.

## End-To-End Validation Script

From Windows PowerShell, configure a real Linux target and run `scripts/validate-linux-agent.ps1`:

```powershell
$env:FILEZALL_LINUX_HOST = "example.com"
$env:FILEZALL_LINUX_USER = "deploy"
$env:FILEZALL_LINUX_PORT = "22"
$env:FILEZALL_LINUX_TOKEN = "replace-with-random-token"
$env:FILEZALL_LINUX_SSH_KEY = "C:\Users\you\.ssh\id_ed25519"
scripts\validate-linux-agent.ps1
```

The script builds the Agent package, uploads it, installs the `filezall-agent` systemd service, opens an `ssh -L` tunnel, checks `/health`, and checks `/resources`.
