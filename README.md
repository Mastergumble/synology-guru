# Synology Guru

A multi-agent system for intelligent monitoring and management of Synology NAS devices.

## Overview

Synology Guru is an automated monitoring solution that uses specialized agents to continuously analyze your Synology NAS health, security, storage, and more. It learns from your system's behavior to establish baselines and detect anomalies.

## Features

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
- **Automated Updates**: Programmatic package upgrades via SPK upload

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

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your Synology credentials
```

5. Run:
```bash
synology-guru
# or
python -m src.orchestrator.main
```

## Configuration

Create a `.env` file with the following settings:

```env
# Synology NAS Connection
SYNOLOGY_HOST=your-nas.synology.me
SYNOLOGY_PORT=5001
SYNOLOGY_HTTPS=true
SYNOLOGY_USERNAME=admin
SYNOLOGY_PASSWORD=your_password

# Email Notifications (optional)
EMAIL_SMTP_HOST=smtp.office365.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your@email.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=your@email.com
EMAIL_TO=recipient@email.com
EMAIL_USE_TLS=true
```

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
│   │   ├── main.py        # Entry point
│   │   ├── orchestrator.py
│   │   └── report.py      # HTML report generator
│   ├── agents/            # Specialized agents
│   │   ├── base.py        # BaseAgent, Priority, Feedback
│   │   ├── learning.py    # LearningAgent with memory
│   │   ├── backup/
│   │   ├── security/
│   │   ├── logs/
│   │   ├── updates/
│   │   ├── storage/
│   │   └── disks/
│   ├── memory/            # Learning system
│   │   ├── models.py      # Observation, Baseline, Pattern
│   │   └── store.py       # Persistent memory store
│   ├── api/               # Synology API client
│   │   └── client.py
│   └── notifications/     # Notification services
│       └── email.py
├── data/                  # Runtime data (auto-generated)
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

## Sample Report

The HTML report includes:

- **System Information**: Model, DSM version, temperature, uptime, RAM
- **Updates**: DSM status and pending package updates
- **Alerts**: Priority-sorted issues requiring attention
- **Storage**: Volume usage with visual progress bars
- **Learning System**: Agent statistics and learned baselines
- **Baselines**: Temperature, disk health, and security metrics

## Tech Stack

- **Language**: Python 3.10+
- **HTTP Client**: httpx (async)
- **Validation**: Pydantic
- **CLI Output**: Rich
- **Persistence**: JSON (learning data)

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Synology DSM Web API
- Built with assistance from Claude (Anthropic)
