# Deploying the backend on an Oracle Cloud Always Free VM

This runs the backend in Docker on one VM, behind Caddy, which serves HTTPS and proxies WebSocket traffic. Only ports 80 and 443 are open. The backend port is never published.

## 1. Create the VM (Oracle console)

1. Compute → Instances → **Create instance**.
2. Image: **Canonical Ubuntu 22.04** or newer.
3. Shape: **VM.Standard.A1.Flex** (Ampere, Always Free). 1 OCPU and 6 GB RAM are enough.
4. Networking: assign a **public IPv4** address. Add your SSH public key.
5. Save the public IP.

## 2. Open ports 80 and 443

In the VCN's **security list** (Networking → Virtual Cloud Networks → your VCN → Security Lists), add ingress rules:

| Source CIDR | Protocol | Destination port |
|---|---|---|
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |

Port 22 for SSH is already open by default.

## 3. Point a domain at the VM

Create an **A record** for a domain or subdomain (for example `api.example.com`) that points to the VM's public IP. Caddy needs this to obtain a TLS certificate. Wait for DNS to resolve before starting the stack.

## 4. Prepare the VM

```bash
ssh ubuntu@<public-ip>
# Get the code. Use the branch you have agreed to deploy.
git clone --branch <deploy-branch> <repo-url> coremind-backend
cd coremind-backend/deploy/oracle
bash setup-vm.sh     # installs Docker and Compose, opens 80/443 on the host firewall
exit                 # log back in so the docker group applies
```

## 5. Configure secrets (on the VM only)

```bash
cd coremind-backend/deploy/oracle
cp backend.env.example backend.env
nano backend.env     # fill in NEBIUS_API_KEY, JWT_SECRET_KEY, and the rest
printf 'DOMAIN=api.example.com\n' > .env
chmod 600 backend.env .env
```

Use a **newly rotated** Nebius key. Generate `JWT_SECRET_KEY` with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

## 6. Start

```bash
docker compose up -d --build
docker compose logs -f backend     # watch for startup errors; Ctrl+C to stop following
curl https://api.example.com/health
```

A signed-out request to a protected route should return `401`. That confirms auth is enforced.

## 7. Update later

```bash
cd coremind-backend && git pull
cd deploy/oracle && docker compose up -d --build
```

Data lives in the `coremind-data` volume and survives rebuilds. Back it up before risky changes:

```bash
docker run --rm -v coremind-data:/data -v "$PWD":/backup alpine tar czf /backup/coremind-data.tgz -C /data .
```

## 8. Connect the desktop app

- HTTP base URL: `https://api.example.com`
- WebSocket URL: `wss://api.example.com/ws`

The desktop stores these in `localStorage` under `coremind:api-base-url` and `coremind:ws-base-url`. Confirm in the app that a settings screen exists for them before relying on it.

## Known limits of this setup

- The container runs as root and dependencies are not pinned. Both are listed as known issues in the repository README.
- The VM is a single point of failure. Back up the data volume.
- CORS allows only the origins in `FRONTEND_ORIGIN`. Check the packaged desktop app's `Origin` header before deploying.
