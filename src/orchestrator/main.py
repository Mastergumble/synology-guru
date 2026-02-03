"""Main entry point for Synology Guru."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.api.client import SynologyClient
from src.memory.store import MemoryStore
from src.orchestrator.orchestrator import SynologyGuru

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


async def async_main() -> None:
    """Async main function."""
    console = Console()
    client = create_client()

    # Initialize shared memory store
    data_dir = Path(__file__).parent.parent.parent / "data"
    memory = MemoryStore(data_dir)

    try:
        # Connect to Synology
        console.print("[dim]Connecting to Synology NAS...[/dim]")
        await client.connect()
        console.print("[green]Connected successfully[/green]")

        # Create and run orchestrator
        guru = create_orchestrator(client, memory)
        await guru.check_health()

        # Show learning status
        show_learning_status(memory, console)

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
