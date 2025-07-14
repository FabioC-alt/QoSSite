#!/bin/bash

set -e

echo "[+] Updating packages..."
sudo apt update

echo "[+] Removing old Docker versions (if any)..."
sudo apt remove -y docker docker-engine docker.io containerd runc || true

echo "[+] Installing required packages..."
sudo apt install -y ca-certificates curl gnupg lsb-release

echo "[+] Adding Docker's official GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "[+] Adding Docker repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "[+] Updating package index with Docker repo..."
sudo apt update

echo "[+] Installing Docker Engine and tools..."
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[+] Verifying Docker installation..."
sudo docker run hello-world

echo "[+] Adding current user ($USER) to docker group..."
sudo usermod -aG docker $USER

echo "[✓] Docker installed successfully!"
echo "→ Please log out and back in or run 'newgrp docker' to use Docker without 'sudo'."
newgrp docker

