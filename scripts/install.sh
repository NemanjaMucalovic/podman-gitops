#!/bin/bash

set -e

# Get the current user
CURRENT_USER=$(whoami)
USER_HOME=$(eval echo ~$CURRENT_USER)

# Create necessary directories in user's home
mkdir -p "$USER_HOME/.local/lib/podman-gitops/repo"
mkdir -p "$USER_HOME/.local/lib/podman-gitops/backups"
mkdir -p "$USER_HOME/.config/podman-gitops"
mkdir -p "$USER_HOME/.config/systemd/user"
mkdir -p "$USER_HOME/.config/containers/systemd"

# Set permissions
chmod -R 755 "$USER_HOME/.local/lib/podman-gitops"
chmod -R 755 "$USER_HOME/.config/podman-gitops"
chmod -R 755 "$USER_HOME/.config/containers/systemd"

# Install Python package for the current user
pip install --user -e .

# Create systemd user service file
cat > "$USER_HOME/.config/systemd/user/podman-gitops.service" << EOF
[Unit]
Description=Podman GitOps Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Environment=HOME=$USER_HOME
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u)
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
ExecStart=$USER_HOME/.local/bin/podman-gitops start --config $USER_HOME/.config/podman-gitops/config.toml
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Reload user's systemd
systemctl --user daemon-reload

echo "Installation complete!"
echo "Please configure $USER_HOME/.config/podman-gitops/config.toml before starting the service"
echo "To start the service, run: systemctl --user start podman-gitops"
echo "To enable the service, run: systemctl --user enable podman-gitops"
echo "To enable lingering (allow service to run without user being logged in), run: sudo loginctl enable-linger $CURRENT_USER" 