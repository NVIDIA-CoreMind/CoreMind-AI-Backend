#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu VM (Oracle Cloud Always Free).
# Installs Docker and Compose, and opens HTTP and HTTPS on the host firewall.
# Review this script before you run it.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 iptables-persistent
sudo usermod -aG docker "$USER"

# Oracle's Ubuntu images ship with a REJECT rule that blocks new ports.
# Insert ACCEPT rules at the top of the chain so SSH access is unchanged.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  fi
done
sudo netfilter-persistent save

echo "Done. Log out and back in so the docker group takes effect."
echo "Also open TCP 80 and 443 in the VCN security list (see deploy/oracle/README.md)."
