# Synology Guru

A multi-agent system for intelligent monitoring and management of Synology NAS devices.

## Overview

Synology Guru is an intelligent, multi-agent monitoring system for Synology NAS devices. It uses six specialized agents to continuously analyze system health, security, storage, backups, logs, and updates. The system learns from your NAS behavior to establish baselines, detect anomalies, and predict potential issues before they become critical.

**Key capabilities:**
- Monitor multiple NAS devices from a single installation
- Six specialized agents working in parallel
- Self-learning baseline establishment and anomaly detection
- Automated HTML reports with email delivery
- Interactive package management and upgrades
- Direct installation on any Python 3.10+ system

## Features

### Multi-NAS Support

Monitor and manage multiple NAS devices from a single installation:

```bash
synology-guru list                # List configured NAS devices
synology-guru check               # Check default NAS
synology-guru check home-nas      # Check specific NAS
synology-guru check --all         # Check all NAS devices
```

### Multi-Agent Architecture

| Agent | Responsibility |
|-------|----------------|
| **Backup Agent** | Monitors Hyper Backup tasks, snapshots, and replication status |
| **Security Agent** | Tracks login attempts, analyzes security threats, monitors firewall |
| **Logs Agent** | Analyzes system logs for errors and anomalies |
| **Updates Agent** | Checks for DSM and package updates |
| **Storage Agent** | Monitors volume capacity and usage trends |
| **Disks Agent** | Tracks disk health via S.M.A.R.T. data and RAID status |

### Intelligent Learning System

- **Baseline Learning**: Automatically establishes normal operating parameters
- **Anomaly Detection**: Uses statistical analysis (z-scores) to detect unusual behavior
- **Pattern Recognition**: Learns recurring patterns and suppresses false positives
- **Trend Analysis**: Predicts potential issues before they occur

### Reporting & Notifications

- **HTML Reports**: Beautiful, detailed reports with system info, alerts, and baselines
- **Email Delivery**: Automatic report delivery via SMTP (supports Microsoft 365, Gmail)
- **Priority-based Alerts**: From Critical (P0) to Info (P4)

### Package Management

- **Update Detection**: Identifies outdated packages from Package Center
- **Interactive Upgrades**: Upgrade packages with confirmation prompts
- **Automated Reports**: Generate and email reports after upgrades

```bash
synology-guru upgrade             # Upgrade with confirmation
synology-guru upgrade home-nas    # Upgrade specific NAS
synology-guru upgrade -y          # Upgrade without prompts
```

## Installation

### Prerequisites

- Python 3.10+
- Access to Synology DSM Web API
- SMTP server for email notifications (optional)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/Mastergumble/synology-guru.git
cd synology-guru
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -e .
```

4. Configure your NAS devices (see Configuration below)

5. Run:
```bash
synology-guru check
```

## Configuration

### Option 1: YAML Configuration (Multi-NAS)

Create `config/nas.yaml` for multiple NAS devices:

```yaml
# Default NAS to use when no name is specified
default: home-nas

# NAS devices configuration
nas:
  home-nas:
    host: 192.168.1.100
    port: 5001
    https: true
    username: ${SYNOLOGY_USERNAME}
    password: ${SYNOLOGY_PASSWORD}

  office-nas:
    host: office.synology.me
    port: 5001
    https: true
    username: ${OFFICE_USER}
    password: ${OFFICE_PASS}

# Email notification settings (optional)
email:
  smtp_host: smtp.office365.com
  smtp_port: 587
  username: ${EMAIL_USERNAME}
  password: ${EMAIL_PASSWORD}
  from_addr: synology@example.com
  to_addr: admin@example.com
  use_tls: true
```

Environment variables can be used with `${VAR}` or `${VAR:-default}` syntax.

### Option 2: Environment Variables (Single NAS)

Create a `.env` file for backward compatibility:

```env
# Synology NAS Connection
SYNOLOGY_HOST=your-nas.synology.me
SYNOLOGY_PORT=5001
SYNOLOGY_HTTPS=true
SYNOLOGY_USERNAME=admin
SYNOLOGY_PASSWORD=your_password

# Additional NAS (optional)
HOME_NAS_HOST=192.168.1.100
HOME_NAS_PORT=5001
HOME_NAS_USERNAME=admin
HOME_NAS_PASSWORD=your_password

# Email Notifications (optional)
EMAIL_SMTP_HOST=smtp.office365.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your@email.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=your@email.com
EMAIL_TO=recipient@email.com
EMAIL_USE_TLS=true
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `synology-guru list` | List all configured NAS devices |
| `synology-guru check [NAS]` | Check health and generate report |
| `synology-guru check --all` | Check all configured NAS devices |
| `synology-guru upgrade [NAS]` | Upgrade packages with confirmation |
| `synology-guru upgrade -y` | Upgrade all packages without prompts |
| `synology-guru learning [NAS]` | Show learning status and patterns |

## Alert Priority Levels

| Priority | Level | Description | Examples |
|----------|-------|-------------|----------|
| **CRITICAL** | P0 | Immediate action required | Disk failure, RAID degraded, backup failed >7 days |
| **HIGH** | P1 | Urgent attention needed | Storage <10%, S.M.A.R.T. errors, security updates |
| **MEDIUM** | P2 | Planned attention | Storage <25%, updates available, certificates expiring |
| **LOW** | P3 | Informational | Backups completed, usage statistics |
| **INFO** | P4 | Logging only | Routine logs, performance metrics |

## Project Structure

```
synology-guru/
├── src/
│   ├── orchestrator/      # Main orchestrator
│   │   ├── main.py        # CLI entry point (Typer)
│   │   ├── orchestrator.py
│   │   └── report.py      # HTML report generator
│   ├── agents/            # Specialized agents
│   │   ├── base.py        # BaseAgent, Priority, Feedback
│   │   ├── learning.py    # LearningAgent with memory
│   │   ├── backup/
│   │   ├── security/
│   │   ├── logs/          # Log analysis and anomaly detection
│   │   ├── updates/
│   │   ├── storage/
│   │   └── disks/
│   ├── config/            # Configuration module
│   │   ├── models.py      # NASConfig, EmailConfig, AppConfig
│   │   └── loader.py      # YAML/env configuration loader
│   ├── memory/            # Learning system
│   │   ├── models.py      # Observation, Baseline, Pattern
│   │   └── store.py       # Persistent memory store
│   ├── api/               # Synology API client
│   │   └── client.py
│   └── notifications/     # Notification services
│       └── email.py
├── config/
│   └── nas.yaml.example   # Example multi-NAS configuration
├── data/                  # Runtime data (per-NAS)
│   ├── home-nas/
│   │   ├── observations.json
│   │   ├── baselines.json
│   │   ├── patterns.json
│   │   └── reports/
│   └── office-nas/
├── .env.example
├── pyproject.toml
└── README.md
```

## API Features

The Synology API client supports:

- **Authentication**: Session-based login with automatic token management
- **Storage**: Volume and disk information
- **System**: DSM info, temperature, uptime
- **Updates**: DSM and package update checking
- **Packages**: List, check updates, and upgrade packages
- **Security**: Connection logs, security scan results
- **Backup**: Hyper Backup task monitoring
- **Logs**: System log retrieval and analysis

## Sample Report

The HTML report includes:

- **System Information**: Model, DSM version, temperature, uptime, RAM
- **Updates**: DSM status and pending package updates
- **Alerts**: Priority-sorted issues requiring attention
- **Storage**: Volume usage with visual progress bars
- **Logs**: Recent errors and anomalies detected by the Logs Agent
- **Learning System**: Agent statistics and learned baselines
- **Baselines**: Temperature, disk health, and security metrics

## Tech Stack

- **Language**: Python 3.10+
- **CLI Framework**: Typer
- **HTTP Client**: httpx (async)
- **Validation**: Pydantic
- **CLI Output**: Rich
- **Configuration**: PyYAML
- **Persistence**: JSON (learning data)

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Synology DSM Web API
- Built with assistance from Claude (Anthropic)

