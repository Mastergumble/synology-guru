"""Main entry point for Synology Guru CLI."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.api.client import SynologyClient
from src.config import AppConfig, ConfigLoader, NASConfig
from src.memory.store import MemoryStore
from src.notifications.email import EmailNotifier, EmailConfig as NotifierEmailConfig
from src.orchestrator.orchestrator import SynologyGuru
from src.orchestrator.report import (
    FullReport,
    ReportGenerator,
    SystemInfo,
    DiskInfo,
    VolumeInfo,
    UpdateInfo,
    PackageUpdate,
)

# Import agents
from src.agents.backup.agent import BackupAgent
from src.agents.security.agent import SecurityAgent
from src.agents.logs.agent import LogsAgent
from src.agents.updates.agent import UpdatesAgent
from src.agents.storage.agent import StorageAgent
from src.agents.disks.agent import DisksAgent


app = typer.Typer(
    name="synology-guru",
    help="Multi-agent system for Synology NAS management and monitoring",
    add_completion=False,
)
console = Console()


def get_config() -> AppConfig:
    """Load application configuration."""
    loader = ConfigLoader()
    return loader.load()


def create_client(nas_config: NASConfig) -> SynologyClient:
    """Create Synology API client from NAS configuration."""
    return SynologyClient(
        host=nas_config.host,
        port=nas_config.port,
        https=nas_config.https,
        username=nas_config.username,
        password=nas_config.password,
    )


def create_email_notifier(config: AppConfig) -> EmailNotifier | None:
    """Create email notifier if configured."""
    if not config.email:
        return None

    notifier_config = NotifierEmailConfig(
        smtp_host=config.email.smtp_host,
        smtp_port=config.email.smtp_port,
        username=config.email.username,
        password=config.email.password,
        from_addr=config.email.from_addr,
        to_addr=config.email.to_addr,
        use_tls=config.email.use_tls,
    )

    return EmailNotifier(notifier_config)


def create_orchestrator(client: SynologyClient, memory: MemoryStore) -> SynologyGuru:
    """Create orchestrator with all learning-enabled agents."""
    guru = SynologyGuru(client)

    guru.register_agents([
        BackupAgent(client, memory),
        SecurityAgent(client, memory),
        LogsAgent(client, memory),
        UpdatesAgent(client, memory),
        StorageAgent(client, memory),
        DisksAgent(client, memory),
    ])

    return guru


def show_learning_status(memory: MemoryStore, nas_name: str) -> None:
    """Display learning status for all agents."""
    console.print()

    table = Table(title=f"Learning Status - {nas_name}")
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
            size_info = vol.get("size", {})
            total = int(size_info.get("total", 0))
            used = int(size_info.get("used", 0))
            free = total - used
            percent = (used / total * 100) if total > 0 else 0

            vol_name = vol.get("vol_desc") or vol.get("id", "Unknown")

            volumes.append(VolumeInfo(
                name=vol_name,
                status=vol.get("status", "unknown"),
                used=format_bytes(used),
                free=format_bytes(free),
                total=format_bytes(total),
                percent=percent,
            ))
    except Exception:
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


async def check_single_nas(
    nas_name: str,
    nas_config: NASConfig,
    app_config: AppConfig,
    send_email: bool = True,
) -> bool:
    """Check a single NAS and generate report. Returns True if successful."""
    client = create_client(nas_config)

    # Initialize memory store for this NAS
    data_dir = app_config.get_data_dir(nas_name)
    data_dir.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore(data_dir)

    # Initialize email notifier
    email_notifier = create_email_notifier(app_config) if send_email else None

    try:
        console.print(f"[dim]Connecting to {nas_name} ({nas_config.host})...[/dim]")
        await client.connect()
        console.print(f"[green]Connected to {nas_name}[/green]")

        # Create and run orchestrator
        guru = create_orchestrator(client, memory)
        feedback = await guru.check_health()

        # Show learning status
        show_learning_status(memory, nas_name)

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
            subject = f"Synology Guru - {nas_name} ({system_info.model}) - "
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
        elif send_email:
            console.print("[yellow]ℹ Email não configurado (ver config/nas.yaml ou .env)[/yellow]")

        return True

    except Exception as e:
        console.print(f"[red]Error checking {nas_name}: {e}[/red]")
        return False
    finally:
        await client.disconnect()


@app.command()
def check(
    nas_name: Annotated[
        Optional[str],
        typer.Argument(help="Name of the NAS to check (uses default if not specified)")
    ] = None,
    all_nas: Annotated[
        bool,
        typer.Option("--all", "-a", help="Check all configured NAS devices")
    ] = False,
    no_email: Annotated[
        bool,
        typer.Option("--no-email", help="Skip sending email notifications")
    ] = False,
) -> None:
    """Check health of NAS device(s) and generate reports."""
    try:
        config = get_config()
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)

    if all_nas:
        # Check all NAS devices
        console.print(f"[bold]Checking all {len(config.nas)} NAS devices...[/bold]")
        console.print()

        results: dict[str, bool] = {}
        for name in config.get_nas_names():
            nas_config = config.get_nas(name)
            console.print(f"[bold cyan]═══ {name} ═══[/bold cyan]")
            results[name] = asyncio.run(
                check_single_nas(name, nas_config, config, send_email=not no_email)
            )
            console.print()

        # Summary
        console.print("[bold]═══ Summary ═══[/bold]")
        for name, success in results.items():
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"  {status} {name}")

        failed = sum(1 for s in results.values() if not s)
        if failed > 0:
            raise typer.Exit(1)
    else:
        # Check single NAS
        target_name = nas_name or config.default
        try:
            nas_config = config.get_nas(target_name)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("[dim]Use 'synology-guru list' to see configured NAS devices[/dim]")
            raise typer.Exit(1)

        console.print(f"[bold]Checking NAS: {target_name}[/bold]")
        console.print()

        success = asyncio.run(
            check_single_nas(target_name, nas_config, config, send_email=not no_email)
        )
        if not success:
            raise typer.Exit(1)


@app.command("list")
def list_nas() -> None:
    """List all configured NAS devices."""
    try:
        config = get_config()
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Configured NAS Devices")
    table.add_column("Name", style="cyan")
    table.add_column("Host")
    table.add_column("Port", justify="right")
    table.add_column("HTTPS")
    table.add_column("Default", style="green")

    for name in config.get_nas_names():
        nas = config.get_nas(name)
        is_default = "✓" if name == config.default else ""
        table.add_row(
            name,
            nas.host,
            str(nas.port),
            "Yes" if nas.https else "No",
            is_default,
        )

    console.print(table)

    if config.email:
        console.print()
        console.print(f"[dim]Email notifications: {config.email.smtp_host}[/dim]")
    else:
        console.print()
        console.print("[dim]Email notifications: not configured[/dim]")


@app.command()
def learning(
    nas_name: Annotated[
        Optional[str],
        typer.Argument(help="Name of the NAS to show learning status for")
    ] = None,
) -> None:
    """Show learning status for a NAS device."""
    try:
        config = get_config()
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)

    target_name = nas_name or config.default

    # Verify NAS exists
    try:
        config.get_nas(target_name)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # Load memory store for this NAS
    data_dir = config.get_data_dir(target_name)
    if not data_dir.exists():
        console.print(f"[yellow]No learning data found for '{target_name}'[/yellow]")
        console.print("[dim]Run 'synology-guru check' first to start collecting data[/dim]")
        raise typer.Exit(0)

    memory = MemoryStore(data_dir)
    show_learning_status(memory, target_name)

    # Show detailed pattern information
    console.print()
    patterns_table = Table(title="Learned Patterns")
    patterns_table.add_column("Agent", style="cyan")
    patterns_table.add_column("Pattern")
    patterns_table.add_column("Confidence", justify="right")
    patterns_table.add_column("Occurrences", justify="right")

    agents = ["backup", "security", "logs", "updates", "storage", "disks"]
    has_patterns = False

    for agent in agents:
        patterns = memory.get_patterns(agent)
        for pattern in patterns:
            has_patterns = True
            conf_color = "green" if pattern.confidence >= 0.7 else "yellow"
            patterns_table.add_row(
                agent,
                pattern.name,
                f"[{conf_color}]{pattern.confidence:.0%}[/{conf_color}]",
                str(pattern.occurrences),
            )

    if has_patterns:
        console.print(patterns_table)
    else:
        console.print("[dim]No patterns learned yet[/dim]")


@app.command()
def upgrade(
    nas_name: Annotated[
        Optional[str],
        typer.Argument(help="Name of the NAS to upgrade packages on")
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts")
    ] = False,
    no_email: Annotated[
        bool,
        typer.Option("--no-email", help="Skip sending email report")
    ] = False,
) -> None:
    """Upgrade packages on a NAS device (with confirmation)."""
    try:
        config = get_config()
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)

    target_name = nas_name or config.default

    try:
        nas_config = config.get_nas(target_name)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    asyncio.run(upgrade_packages(target_name, nas_config, config, skip_confirm=yes, send_email=not no_email))


async def upgrade_packages(
    nas_name: str,
    nas_config: NASConfig,
    app_config: AppConfig,
    skip_confirm: bool = False,
    send_email: bool = True,
) -> None:
    """Check for and upgrade packages on a NAS."""
    client = create_client(nas_config)
    upgraded_packages: list[str] = []

    try:
        console.print(f"[dim]Connecting to {nas_name} ({nas_config.host})...[/dim]")
        await client.connect()
        console.print(f"[green]Connected to {nas_name}[/green]")
        console.print()

        # Get available updates
        console.print("[dim]A verificar atualizações...[/dim]")
        updates = await client.get_package_updates()

        if not updates:
            console.print("[green]✓ Todos os pacotes estão atualizados![/green]")
            return

        # Show available updates
        table = Table(title=f"Atualizações disponíveis - {nas_name}")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Pacote", style="cyan")
        table.add_column("Versão Atual")
        table.add_column("Nova Versão", style="green")

        for i, pkg in enumerate(updates, 1):
            table.add_row(
                str(i),
                pkg["name"],
                pkg["installed_version"],
                pkg["available_version"],
            )

        console.print(table)
        console.print()

        # Ask for confirmation
        if not skip_confirm:
            confirm = typer.confirm(
                f"Deseja atualizar {len(updates)} pacote(s)?",
                default=False,
            )
            if not confirm:
                console.print("[yellow]Atualização cancelada.[/yellow]")
                return

        # Perform upgrades
        console.print()
        console.print("[bold]A atualizar pacotes...[/bold]")

        success_count = 0
        fail_count = 0

        for pkg in updates:
            pkg_name = pkg["name"]
            pkg_id = pkg["id"]

            if not skip_confirm:
                pkg_confirm = typer.confirm(
                    f"Atualizar {pkg_name} ({pkg['installed_version']} -> {pkg['available_version']})?",
                    default=True,
                )
                if not pkg_confirm:
                    console.print(f"[yellow]  ⊘ {pkg_name} - ignorado[/yellow]")
                    continue

            console.print(f"[dim]  ↻ A atualizar {pkg_name}...[/dim]")

            try:
                result = await client.upgrade_package(pkg_id)
                console.print(f"[green]  ✓ {pkg_name} atualizado para {result.get('version', pkg['available_version'])}[/green]")
                success_count += 1
                upgraded_packages.append(f"{pkg_name}: {pkg['installed_version']} -> {pkg['available_version']}")
            except Exception as e:
                console.print(f"[red]  ✗ {pkg_name} - Erro: {e}[/red]")
                fail_count += 1

        # Summary
        console.print()
        if success_count > 0:
            console.print(f"[green]✓ {success_count} pacote(s) atualizado(s) com sucesso[/green]")
        if fail_count > 0:
            console.print(f"[red]✗ {fail_count} pacote(s) falharam[/red]")

        # Generate report and send email if packages were upgraded
        if upgraded_packages and send_email:
            console.print()
            console.print("[dim]A gerar relatório...[/dim]")
            await generate_upgrade_report(nas_name, nas_config, app_config, upgraded_packages)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    finally:
        await client.disconnect()


async def generate_upgrade_report(
    nas_name: str,
    nas_config: NASConfig,
    app_config: AppConfig,
    upgraded_packages: list[str],
) -> None:
    """Generate a full report after upgrades and send via email."""
    client = create_client(nas_config)

    # Initialize memory store for this NAS
    data_dir = app_config.get_data_dir(nas_name)
    data_dir.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore(data_dir)

    # Initialize email notifier
    email_notifier = create_email_notifier(app_config)

    try:
        await client.connect()

        # Create and run orchestrator
        guru = create_orchestrator(client, memory)
        feedback = await guru.check_health()

        # Collect info for full report
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

        # Add upgrade summary to reports
        upgrade_summary = "\n\nPacotes Atualizados:\n" + "\n".join(f"  - {pkg}" for pkg in upgraded_packages)
        text_report += upgrade_summary
        html_report = html_report.replace(
            "</body>",
            f"<h2>Pacotes Atualizados</h2><ul>{''.join(f'<li>{pkg}</li>' for pkg in upgraded_packages)}</ul></body>"
        )

        # Save report to file
        reports_dir = data_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        report_file = reports_dir / f"upgrade_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_file.write_text(html_report, encoding="utf-8")
        console.print(f"[green]✓ Relatório guardado:[/green] {report_file}")

        # Send email if configured
        if email_notifier:
            console.print("[dim]A enviar email...[/dim]")
            subject = f"Synology Guru - {nas_name} - Pacotes Atualizados ({len(upgraded_packages)})"

            if email_notifier.send(subject, html_report, text_report):
                console.print("[green]✓ Email enviado com sucesso![/green]")
            else:
                console.print("[red]✗ Falha ao enviar email[/red]")
        else:
            console.print("[yellow]ℹ Email não configurado[/yellow]")

    finally:
        await client.disconnect()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
