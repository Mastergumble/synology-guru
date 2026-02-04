"""Main entry point for Synology Guru."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.api.client import SynologyClient
from src.memory.store import MemoryStore
from src.orchestrator.orchestrator import SynologyGuru
from src.orchestrator.report import (
    ReportGenerator,
    FullReport,
    SystemInfo,
    DiskInfo,
    VolumeInfo,
    UpdateInfo,
    PackageUpdate,
)
from src.notifications.email import EmailNotifier, EmailConfig

# Import agents
from src.agents.backup.agent import BackupAgent
from src.agents.security.agent import SecurityAgent
from src.agents.logs.agent import LogsAgent
from src.agents.updates.agent import UpdatesAgent
from src.agents.storage.agent import StorageAgent
from src.agents.disks.agent import DisksAgent


def create_client() -> SynologyClient:
    """Create Synology API client from environment variables."""
    load_dotenv()

    host = os.getenv("SYNOLOGY_HOST")
    if not host:
        print("Error: SYNOLOGY_HOST not configured in .env")
        sys.exit(1)

    return SynologyClient(
        host=host,
        port=int(os.getenv("SYNOLOGY_PORT", "5001")),
        https=os.getenv("SYNOLOGY_HTTPS", "true").lower() == "true",
        username=os.getenv("SYNOLOGY_USERNAME", ""),
        password=os.getenv("SYNOLOGY_PASSWORD", ""),
    )


def create_email_notifier() -> EmailNotifier | None:
    """Create email notifier if configured."""
    smtp_host = os.getenv("EMAIL_SMTP_HOST")
    if not smtp_host:
        return None

    config = EmailConfig(
        smtp_host=smtp_host,
        smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
        username=os.getenv("EMAIL_USERNAME", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
        from_addr=os.getenv("EMAIL_FROM", ""),
        to_addr=os.getenv("EMAIL_TO", ""),
        use_tls=os.getenv("EMAIL_USE_TLS", "true").lower() == "true",
    )

    return EmailNotifier(config)


def create_orchestrator(client: SynologyClient, memory: MemoryStore) -> SynologyGuru:
    """Create orchestrator with all learning-enabled agents."""
    guru = SynologyGuru(client)

    # Register all specialized agents with shared memory
    # All agents now support learning
    guru.register_agents([
        BackupAgent(client, memory),
        SecurityAgent(client, memory),
        LogsAgent(client, memory),
        UpdatesAgent(client, memory),
        StorageAgent(client, memory),
        DisksAgent(client, memory),
    ])

    return guru


def show_learning_status(memory: MemoryStore, console: Console) -> None:
    """Display learning status for all agents."""
    console.print()

    table = Table(title="Learning Status")
    table.add_column("Agent", style="cyan")
    table.add_column("Observations", justify="right")
    table.add_column("Baselines", justify="right")
    table.add_column("Patterns", justify="right")
    table.add_column("Active Patterns", justify="right", style="green")

    agents = ["backup", "security", "logs", "updates", "storage", "disks"]

    for agent in agents:
        insights = memory.get_insights(agent)
        table.add_row(
            agent,
            str(insights["total_observations"]),
            str(insights["baselines_learned"]),
            str(insights["patterns_learned"]),
            str(insights["active_patterns"]),
        )

    console.print(table)


def get_learning_data(memory: MemoryStore) -> dict[str, dict]:
    """Get learning data for all agents."""
    agents = ["backup", "security", "logs", "updates", "storage", "disks"]
    return {agent: memory.get_insights(agent) for agent in agents}


async def collect_system_info(client: SynologyClient) -> SystemInfo:
    """Collect system information."""
    try:
        info = await client.get_dsm_info()
        return SystemInfo(
            model=info.get("model", "Unknown"),
            serial=info.get("serial", ""),
            dsm_version=info.get("version_string", ""),
            temperature=info.get("temperature", 0),
            uptime=info.get("uptime", 0),
            ram=info.get("ram", 0),
        )
    except Exception:
        return SystemInfo()


async def collect_disk_info(client: SynologyClient) -> list[DiskInfo]:
    """Collect disk information."""
    disks = []
    try:
        data = await client.get_disk_info()
        for disk in data.get("disks", []):
            disks.append(DiskInfo(
                name=disk.get("name", disk.get("id", "Unknown")),
                status=disk.get("status", "unknown"),
                temperature=disk.get("temp", 0),
                bad_sectors=disk.get("bad_sector_count", 0) or 0,
                model=disk.get("model", ""),
                size=format_bytes(disk.get("size_total", 0)),
            ))
    except Exception:
        pass
    return disks


async def collect_volume_info(client: SynologyClient) -> list[VolumeInfo]:
    """Collect volume information."""
    volumes = []
    try:
        data = await client.get_storage_info()
        for vol in data.get("volumes", []):
            # Get size info - values may be strings
            size_info = vol.get("size", {})
            total = int(size_info.get("total", 0))
            used = int(size_info.get("used", 0))
            free = total - used
            percent = (used / total * 100) if total > 0 else 0

            # Get volume description or ID
            vol_name = vol.get("vol_desc") or vol.get("id", "Unknown")

            volumes.append(VolumeInfo(
                name=vol_name,
                status=vol.get("status", "unknown"),
                used=format_bytes(used),
                free=format_bytes(free),
                total=format_bytes(total),
                percent=percent,
            ))
    except Exception as e:
        # Try alternate API
        try:
            data = await client.get_volume_info()
            for vol in data.get("vol_info", []):
                total = int(vol.get("total_size", 0))
                used = int(vol.get("used_size", 0))
                free = total - used
                percent = (used / total * 100) if total > 0 else 0

                vol_name = vol.get("vol_desc") or vol.get("name", "Unknown")

                volumes.append(VolumeInfo(
                    name=vol_name,
                    status=vol.get("status", "unknown"),
                    used=format_bytes(used),
                    free=format_bytes(free),
                    total=format_bytes(total),
                    percent=percent,
                ))
        except Exception:
            pass
    return volumes


async def collect_update_info(client: SynologyClient) -> UpdateInfo:
    """Collect update information."""
    try:
        dsm_info = await client.get_dsm_info()
        update_info = await client.check_updates()

        available = update_info.get("available", False)
        new_version = update_info.get("version", "")
        update_type = update_info.get("type", "")
        is_security = "security" in update_type.lower()

        # Get package updates
        package_updates = []
        try:
            pkg_updates = await client.get_package_updates()
            for pkg in pkg_updates:
                package_updates.append(PackageUpdate(
                    name=pkg["name"],
                    installed_version=pkg["installed_version"],
                    available_version=pkg["available_version"],
                ))
        except Exception:
            pass

        return UpdateInfo(
            available=available,
            current_version=dsm_info.get("version_string", "Unknown"),
            new_version=new_version if available else "",
            is_security=is_security,
            reboot_needed=update_info.get("reboot_needed", False),
            package_updates=package_updates if package_updates else None,
        )
    except Exception:
        return UpdateInfo()


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable string."""
    if bytes_val == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while bytes_val >= 1024 and i < len(units) - 1:
        bytes_val /= 1024
        i += 1
    return f"{bytes_val:.1f} {units[i]}"


async def async_main() -> None:
    """Async main function."""
    console = Console()
    client = create_client()

    # Initialize shared memory store
    data_dir = Path(__file__).parent.parent.parent / "data"
    memory = MemoryStore(data_dir)

    # Initialize email notifier
    email_notifier = create_email_notifier()

    try:
        # Connect to Synology
        console.print("[dim]Connecting to Synology NAS...[/dim]")
        await client.connect()
        console.print("[green]Connected successfully[/green]")

        # Create and run orchestrator
        guru = create_orchestrator(client, memory)
        feedback = await guru.check_health()

        # Show learning status
        show_learning_status(memory, console)

        # Collect additional info for full report
        console.print()
        console.print("[dim]A gerar relatório completo...[/dim]")

        system_info = await collect_system_info(client)
        disk_info = await collect_disk_info(client)
        volume_info = await collect_volume_info(client)
        update_info = await collect_update_info(client)
        learning_data = get_learning_data(memory)

        # Create full report
        report = FullReport(
            timestamp=datetime.now(),
            system=system_info,
            disks=disk_info,
            volumes=volume_info,
            feedback=feedback,
            learning=learning_data,
            updates=update_info,
        )

        # Generate HTML report
        report_generator = ReportGenerator(memory)
        html_report = report_generator.generate_html(report)
        text_report = report_generator.generate_text(report)

        # Save report to file
        reports_dir = data_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        report_file = reports_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_file.write_text(html_report, encoding="utf-8")
        console.print(f"[green]✓ Relatório guardado:[/green] {report_file}")

        # Send email if configured
        if email_notifier:
            console.print("[dim]A enviar email...[/dim]")
            subject = f"Synology Guru - {system_info.model} - "
            if report.has_critical_alerts():
                subject += "🔴 CRÍTICO"
            elif report.has_high_alerts():
                subject += "🟠 ATENÇÃO"
            else:
                subject += "🟢 OK"

            if email_notifier.send(subject, html_report, text_report):
                console.print("[green]✓ Email enviado com sucesso![/green]")
            else:
                console.print("[red]✗ Falha ao enviar email[/red]")
        else:
            console.print("[yellow]ℹ Email não configurado (ver .env)[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise
    finally:
        await client.disconnect()


def main() -> None:
    """Main entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
