"""Report generator for Synology Guru."""

from datetime import datetime
from dataclasses import dataclass

from src.agents.base import Feedback, Priority
from src.memory.store import MemoryStore


@dataclass
class SystemInfo:
    """System information for report."""

    model: str = ""
    serial: str = ""
    dsm_version: str = ""
    temperature: int = 0
    uptime: int = 0
    ram: int = 0


@dataclass
class DiskInfo:
    """Disk information for report."""

    name: str
    status: str
    temperature: int
    bad_sectors: int
    model: str = ""
    size: str = ""


@dataclass
class VolumeInfo:
    """Volume information for report."""

    name: str
    status: str
    used: str
    free: str
    total: str
    percent: float


@dataclass
class PackageUpdate:
    """Package update information."""

    name: str
    installed_version: str
    available_version: str


@dataclass
class UpdateInfo:
    """Update information for report."""

    available: bool = False
    current_version: str = ""
    new_version: str = ""
    is_security: bool = False
    reboot_needed: bool = False
    package_updates: list[PackageUpdate] | None = None


@dataclass
class FullReport:
    """Complete report data."""

    timestamp: datetime
    system: SystemInfo
    disks: list[DiskInfo]
    volumes: list[VolumeInfo]
    feedback: list[Feedback]
    learning: dict[str, dict]
    updates: UpdateInfo | None = None

    def has_critical_alerts(self) -> bool:
        """Check if there are critical alerts."""
        return any(f.priority == Priority.CRITICAL for f in self.feedback)

    def has_high_alerts(self) -> bool:
        """Check if there are high priority alerts."""
        return any(f.priority == Priority.HIGH for f in self.feedback)

    def alert_count_by_priority(self) -> dict[Priority, int]:
        """Count alerts by priority."""
        counts = {p: 0 for p in Priority}
        for f in self.feedback:
            counts[f.priority] += 1
        return counts


class ReportGenerator:
    """Generate HTML reports."""

    def __init__(self, memory: MemoryStore) -> None:
        """Initialize report generator."""
        self.memory = memory

    def generate_html(self, report: FullReport) -> str:
        """Generate HTML report."""
        alerts_html = self._generate_alerts_html(report.feedback)
        system_html = self._generate_system_html(report.system)
        updates_html = self._generate_updates_html(report.updates)
        disks_html = self._generate_disks_html(report.disks)
        volumes_html = self._generate_volumes_html(report.volumes)
        learning_html = self._generate_learning_html(report.learning)
        baselines_html = self._generate_baselines_html()

        # Determine status color
        if report.has_critical_alerts():
            status_color = "#dc3545"
            status_text = "CRITICAL"
            status_emoji = "🔴"
        elif report.has_high_alerts():
            status_color = "#fd7e14"
            status_text = "WARNING"
            status_emoji = "🟠"
        else:
            status_color = "#28a745"
            status_text = "OK"
            status_emoji = "🟢"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Synology Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1a237e 0%, #3949ab 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .header .subtitle {{
            opacity: 0.8;
            margin-top: 8px;
        }}
        .status-banner {{
            background: {status_color};
            color: white;
            padding: 15px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section h2 {{
            color: #1a237e;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #555;
        }}
        tr:hover {{
            background: #fafafa;
        }}
        .alert {{
            padding: 12px 15px;
            border-radius: 6px;
            margin-bottom: 10px;
        }}
        .alert-critical {{
            background: #ffebee;
            border-left: 4px solid #dc3545;
        }}
        .alert-high {{
            background: #fff3e0;
            border-left: 4px solid #fd7e14;
        }}
        .alert-medium {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
        }}
        .alert-low {{
            background: #e8f5e9;
            border-left: 4px solid #28a745;
        }}
        .alert-info {{
            background: #f5f5f5;
            border-left: 4px solid #9e9e9e;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-ok {{
            background: #e8f5e9;
            color: #28a745;
        }}
        .badge-warn {{
            background: #fff3e0;
            color: #fd7e14;
        }}
        .badge-error {{
            background: #ffebee;
            color: #dc3545;
        }}
        .no-alerts {{
            text-align: center;
            padding: 40px;
            color: #28a745;
            font-size: 18px;
        }}
        .footer {{
            background: #f5f5f5;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 14px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .metric-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .metric-label {{
            font-size: 11px;
            color: #666;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: bold;
            color: #1a237e;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ Synology Report</h1>
            <div class="subtitle">Status Report - {report.timestamp.strftime('%d/%m/%Y %H:%M')}</div>
        </div>

        <div class="status-banner">
            {status_emoji} Overall Status: {status_text}
        </div>

        <div class="content">
            {system_html}
            {updates_html}
            {alerts_html}
            {volumes_html}
            {disks_html}
            {learning_html}
            {baselines_html}
        </div>

        <div class="footer">
            Generated by Trilobyte Services • {report.timestamp.strftime('%d/%m/%Y %H:%M:%S')}
        </div>
    </div>
</body>
</html>"""

        return html

    def _generate_system_html(self, system: SystemInfo) -> str:
        """Generate system info HTML."""
        uptime_hours = system.uptime // 3600
        uptime_days = uptime_hours // 24
        uptime_str = f"{uptime_days}d {uptime_hours % 24}h" if uptime_days > 0 else f"{uptime_hours}h"

        return f"""
        <div class="section">
            <h2>📊 System Information</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-label">Model</div>
                    <div class="metric-value">{system.model}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">DSM Version</div>
                    <div class="metric-value">{system.dsm_version}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Temperature</div>
                    <div class="metric-value">{system.temperature}°C</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Uptime</div>
                    <div class="metric-value">{uptime_str}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">RAM</div>
                    <div class="metric-value">{system.ram} MB</div>
                </div>
            </div>
        </div>"""

    def _generate_updates_html(self, updates: UpdateInfo | None) -> str:
        """Generate updates HTML."""
        if updates is None:
            return ""

        if updates.available:
            if updates.is_security:
                badge = '<span class="badge badge-error">SECURITY</span>'
                status_text = f"Security update available: {updates.new_version}"
            else:
                badge = '<span class="badge badge-warn">AVAILABLE</span>'
                status_text = f"New version available: {updates.new_version}"
        else:
            badge = '<span class="badge badge-ok">UP TO DATE</span>'
            status_text = ""

        reboot_warning = ""
        if updates.reboot_needed:
            reboot_warning = '<div class="alert alert-medium" style="margin-top:15px">⚠️ Reboot required to complete updates</div>'

        # Package updates section
        package_html = ""
        if updates.package_updates:
            package_rows = ""
            for pkg in updates.package_updates:
                package_rows += f"""
                <tr>
                    <td>{pkg.name}</td>
                    <td>{pkg.installed_version}</td>
                    <td><strong>{pkg.available_version}</strong></td>
                </tr>"""

            package_html = f"""
            <h3 style="margin-top:20px">📦 Package Updates ({len(updates.package_updates)})</h3>
            <table>
                <thead>
                    <tr>
                        <th>Package</th>
                        <th>Installed Version</th>
                        <th>Available Version</th>
                    </tr>
                </thead>
                <tbody>
                    {package_rows}
                </tbody>
            </table>"""
        else:
            package_html = '<p style="margin-top:15px;color:#28a745">✅ All packages are up to date</p>'

        status_cell = f"{status_text} {badge}" if status_text else badge

        return f"""
        <div class="section">
            <h2>🔄 Updates</h2>
            <table>
                <tr>
                    <td><strong>DSM Version</strong></td>
                    <td>{updates.current_version}</td>
                </tr>
                <tr>
                    <td><strong>DSM Status</strong></td>
                    <td>{status_cell}</td>
                </tr>
            </table>
            {reboot_warning}
            {package_html}
        </div>"""

    def _generate_alerts_html(self, feedback: list[Feedback]) -> str:
        """Generate alerts HTML."""
        if not feedback:
            return """
        <div class="section">
            <h2>🔔 Alerts</h2>
            <div class="no-alerts">✅ No alerts. Everything is OK.</div>
        </div>"""

        alerts = ""
        priority_class = {
            Priority.CRITICAL: "alert-critical",
            Priority.HIGH: "alert-high",
            Priority.MEDIUM: "alert-medium",
            Priority.LOW: "alert-low",
            Priority.INFO: "alert-info",
        }

        for f in sorted(feedback, key=lambda x: x.priority):
            css_class = priority_class.get(f.priority, "alert-info")
            details = f"<br><small style='color:#666'>{f.details}</small>" if f.details else ""
            alerts += f"""
            <div class="alert {css_class}">
                <strong>{f.priority.emoji} [{f.category}]</strong> {f.message}{details}
            </div>"""

        return f"""
        <div class="section">
            <h2>🔔 Alerts</h2>
            {alerts}
        </div>"""

    def _generate_disks_html(self, disks: list[DiskInfo]) -> str:
        """Generate disks HTML."""
        if not disks:
            return ""

        rows = ""
        for d in disks:
            if d.status.lower() in ["normal", "healthy", "initialized"]:
                badge = '<span class="badge badge-ok">OK</span>'
            elif d.status.lower() in ["warning"]:
                badge = '<span class="badge badge-warn">WARNING</span>'
            else:
                badge = f'<span class="badge badge-error">{d.status}</span>'

            rows += f"""
            <tr>
                <td><strong>{d.name}</strong></td>
                <td>{d.model}</td>
                <td>{d.size}</td>
                <td>{d.temperature}°C</td>
                <td>{d.bad_sectors}</td>
                <td>{badge}</td>
            </tr>"""

        return f"""
        <div class="section">
            <h2>💾 Disks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Disk</th>
                        <th>Model</th>
                        <th>Size</th>
                        <th>Temp.</th>
                        <th>Bad Sectors</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""

    def _generate_volumes_html(self, volumes: list[VolumeInfo]) -> str:
        """Generate volumes HTML."""
        if not volumes:
            return """
        <div class="section">
            <h2>📁 Storage</h2>
            <div class="no-alerts">ℹ️ Volume information not available</div>
        </div>"""

        rows = ""
        for v in volumes:
            if v.percent < 80:
                badge = '<span class="badge badge-ok">OK</span>'
            elif v.percent < 90:
                badge = '<span class="badge badge-warn">WARNING</span>'
            else:
                badge = '<span class="badge badge-error">CRITICAL</span>'

            # Progress bar
            bar_color = "#28a745" if v.percent < 80 else "#fd7e14" if v.percent < 90 else "#dc3545"
            progress = f"""
            <div style="background:#e0e0e0;border-radius:4px;height:8px;width:120px;display:inline-block;margin-right:10px">
                <div style="background:{bar_color};border-radius:4px;height:8px;width:{min(v.percent, 100)}%"></div>
            </div>
            <strong>{v.percent:.1f}%</strong>"""

            free_percent = 100 - v.percent

            rows += f"""
            <tr>
                <td><strong>{v.name}</strong></td>
                <td>{v.used}</td>
                <td>{v.free} ({free_percent:.1f}% free)</td>
                <td>{v.total}</td>
                <td>{progress}</td>
                <td>{badge}</td>
            </tr>"""

        return f"""
        <div class="section">
            <h2>📁 Storage</h2>
            <table>
                <thead>
                    <tr>
                        <th>Volume</th>
                        <th>Used</th>
                        <th>Free</th>
                        <th>Total</th>
                        <th>Usage</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""

    def _generate_learning_html(self, learning: dict[str, dict]) -> str:
        """Generate learning status HTML."""
        rows = ""
        for agent, stats in learning.items():
            rows += f"""
            <tr>
                <td><strong>{agent}</strong></td>
                <td>{stats.get('total_observations', 0)}</td>
                <td>{stats.get('baselines_learned', 0)}</td>
                <td>{stats.get('patterns_learned', 0)}</td>
                <td>{stats.get('active_patterns', 0)}</td>
            </tr>"""

        return f"""
        <div class="section">
            <h2>🧠 Learning System</h2>
            <table>
                <thead>
                    <tr>
                        <th>Agent</th>
                        <th>Observations</th>
                        <th>Baselines</th>
                        <th>Patterns</th>
                        <th>Active Patterns</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>"""

    def _generate_baselines_html(self) -> str:
        """Generate baselines HTML from memory store."""
        baselines = list(self.memory._baselines.values())

        if not baselines:
            return ""

        # Group baselines by category
        temp_baselines = []
        disk_baselines = []
        security_baselines = []
        other_baselines = []

        for b in baselines:
            if b.metric.startswith("temp_"):
                temp_baselines.append(b)
            elif "disk" in b.metric.lower() or "bad_sectors" in b.metric.lower() or "raid" in b.metric.lower():
                disk_baselines.append(b)
            elif "login" in b.metric.lower() or "ip" in b.metric.lower():
                security_baselines.append(b)
            else:
                other_baselines.append(b)

        html = '<div class="section"><h2>📈 Learned Baselines</h2>'

        if temp_baselines:
            html += "<h3>🌡️ Temperatures</h3><table><thead><tr><th>Metric</th><th>Average</th><th>Std Dev</th><th>Min</th><th>Max</th><th>Samples</th></tr></thead><tbody>"
            for b in sorted(temp_baselines, key=lambda x: x.metric):
                metric_name = self._format_metric_name(b.metric)
                html += f"<tr><td>{metric_name}</td><td>{b.mean:.1f}°C</td><td>±{b.std_dev:.2f}</td><td>{b.min_value:.0f}</td><td>{b.max_value:.0f}</td><td>{b.sample_count}</td></tr>"
            html += "</tbody></table>"

        if disk_baselines:
            html += "<h3>💾 Disks</h3><table><thead><tr><th>Metric</th><th>Average</th><th>Std Dev</th><th>Min</th><th>Max</th><th>Samples</th></tr></thead><tbody>"
            for b in sorted(disk_baselines, key=lambda x: x.metric):
                metric_name = self._format_metric_name(b.metric)
                html += f"<tr><td>{metric_name}</td><td>{b.mean:.2f}</td><td>±{b.std_dev:.2f}</td><td>{b.min_value:.0f}</td><td>{b.max_value:.0f}</td><td>{b.sample_count}</td></tr>"
            html += "</tbody></table>"

        if security_baselines:
            html += "<h3>🔒 Security</h3><table><thead><tr><th>Metric</th><th>Average</th><th>Std Dev</th><th>Min</th><th>Max</th><th>Samples</th></tr></thead><tbody>"
            for b in sorted(security_baselines, key=lambda x: x.metric):
                metric_name = self._format_metric_name(b.metric)
                html += f"<tr><td>{metric_name}</td><td>{b.mean:.2f}</td><td>±{b.std_dev:.2f}</td><td>{b.min_value:.0f}</td><td>{b.max_value:.0f}</td><td>{b.sample_count}</td></tr>"
            html += "</tbody></table>"

        html += "</div>"
        return html

    def _format_metric_name(self, metric: str) -> str:
        """Format metric name for display."""
        # Mapping of raw metric names to formatted display names
        replacements = {
            "temp_": "",
            "bad_sectors_": "Bad Sectors ",
            "disk_health_rate": "Disk Health Rate",
            "healthy_disk_count": "Healthy Disk Count",
            "raid_healthy_reuse_1": "RAID Healthy Reuse",
            "total_disk_count": "Total Disk Count",
            "failed_logins_24h": "Failed Logins 24h",
            "successful_logins_24h": "Successful Logins 24h",
            "unique_ips_failed": "Unique IPs Failed",
            "update_available": "Update Available",
        }

        result = metric
        for old, new in replacements.items():
            if old in result:
                result = result.replace(old, new)

        return result

    def generate_text(self, report: FullReport) -> str:
        """Generate plain text report."""
        lines = [
            "=" * 60,
            "SYNOLOGY REPORT - Status Report",
            f"Data: {report.timestamp.strftime('%d/%m/%Y %H:%M')}",
            "=" * 60,
            "",
            "SISTEMA",
            "-" * 40,
            f"Modelo: {report.system.model}",
            f"DSM: {report.system.dsm_version}",
            f"Temperatura: {report.system.temperature}°C",
            f"RAM: {report.system.ram} MB",
            "",
        ]

        # Updates
        if report.updates:
            lines.append("ATUALIZAÇÕES")
            lines.append("-" * 40)
            lines.append(f"Versão DSM: {report.updates.current_version}")
            if report.updates.available:
                update_type = "SEGURANÇA" if report.updates.is_security else "Disponível"
                lines.append(f"⚠️ Atualização DSM [{update_type}]: {report.updates.new_version}")
            else:
                lines.append("✅ DSM atualizado")
            if report.updates.reboot_needed:
                lines.append("⚠️ Reinício necessário")

            # Package updates
            if report.updates.package_updates:
                lines.append(f"\n📦 Pacotes com atualizações ({len(report.updates.package_updates)}):")
                for pkg in report.updates.package_updates:
                    lines.append(f"  • {pkg.name}: {pkg.installed_version} → {pkg.available_version}")
            else:
                lines.append("✅ Todos os pacotes atualizados")
            lines.append("")

        # Volumes/Storage
        if report.volumes:
            lines.append("ARMAZENAMENTO")
            lines.append("-" * 40)
            for v in report.volumes:
                free_percent = 100 - v.percent
                lines.append(f"{v.name}: {v.used} usado / {v.free} livre ({free_percent:.1f}%) / {v.total} total | {v.percent:.1f}% ocupado")
            lines.append("")

        # Alerts
        lines.append("ALERTAS")
        lines.append("-" * 40)
        if not report.feedback:
            lines.append("✅ Sem alertas. Tudo em ordem.")
        else:
            for f in sorted(report.feedback, key=lambda x: x.priority):
                lines.append(f"{f.priority.emoji} [{f.category}] {f.message}")
                if f.details:
                    lines.append(f"   {f.details}")
        lines.append("")

        # Disks
        if report.disks:
            lines.append("DISCOS")
            lines.append("-" * 40)
            for d in report.disks:
                lines.append(f"{d.name}: {d.temperature}°C | Bad sectors: {d.bad_sectors} | {d.status}")
            lines.append("")

        # Learning
        lines.append("APRENDIZAGEM")
        lines.append("-" * 40)
        for agent, stats in report.learning.items():
            lines.append(f"{agent}: {stats.get('total_observations', 0)} obs, {stats.get('baselines_learned', 0)} baselines")
        lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
