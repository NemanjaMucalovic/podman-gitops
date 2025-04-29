# Podman GitOps

A lightweight GitOps tool designed specifically for managing Podman container deployments using quadlet files. This tool follows the GitOps principle of using Git as the single source of truth for declarative infrastructure and applications.

## Features

- Git-based deployment management
- Podman quadlet file support
- Prometheus metrics integration
- Health checking and rollback capabilities
- Secret management
- Notification system

## Requirements

- Python 3.8 or higher
- Podman with quadlet support
- Systemd

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/podman-gitops.git
cd podman-gitops
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -e .
```

## Configuration

Create a `config.toml` file in the project root with your settings:

```toml
[git]
repository_url = "https://github.com/yourusername/your-repo.git"
branch = "main"
poll_interval = 300

[podman]
quadlet_dir = "/etc/containers/systemd"
backup_dir = "/var/lib/podman-gitops/backups"

[metrics]
enabled = true
port = 8000
host = "0.0.0.0"
```

## Usage

Start the service:

```bash
python src/main.py
```

The service will:
1. Poll the configured Git repository for changes
2. Process quadlet files
3. Deploy containers using Podman
4. Monitor container health
5. Expose metrics on the configured port

## Development

1. Install development dependencies:
```bash
pip install -e ".[dev]"
```

2. Run tests:
```bash
pytest
```

3. Run linting:
```bash
ruff check .
```

## License

MIT License 