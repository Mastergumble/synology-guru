"""Synology Guru - Main orchestrator for Synology NAS management."""

import asyncio
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.agents.base import BaseAgent, Feedback, Priority
from src.api.client import SynologyClient


@dataclass
class AgentResult:
    """Result from an agent execution."""

    agent_name: str
    feedback: list[Feedback]
    error: str | None = None


class SynologyGuru:
    """Main orchestrator that coordinates all specialized agents."""

    def __init__(self, client: SynologyClient) -> None:
        """Initialize orchestrator with API client."""
        self.client = client
        self.agents: list[BaseAgent] = []
        self.console = Console()

    def register_agent(self, agent: BaseAgent) -> None:
        """Register a specialized agent."""
        self.agents.append(agent)

    def register_agents(self, agents: list[BaseAgent]) -> None:
        """Register multiple agents."""
        self.agents.extend(agents)

    async def run_agent(self, agent: BaseAgent) -> AgentResult:
        """Run a single agent and capture results."""
        try:
            feedback = await agent.run()
            return AgentResult(agent_name=agent.name, feedback=feedback)
        except Exception as e:
            return AgentResult(
                agent_name=agent.name,
                feedback=[],
                error=str(e),
            )

    async def run_all_agents(self) -> list[AgentResult]:
        """Run all registered agents concurrently."""
        tasks = [self.run_agent(agent) for agent in self.agents]
        return await asyncio.gather(*tasks)

    def aggregate_feedback(
        self,
        results: list[AgentResult],
        min_priority: Priority = Priority.LOW,
    ) -> list[Feedback]:
        """Aggregate and sort feedback from all agents."""
        all_feedback: list[Feedback] = []

        for result in results:
            if result.error:
                # Report agent errors as high priority
                all_feedback.append(
                    Feedback(
                        priority=Priority.HIGH,
                        category=result.agent_name,
                        message=f"Agent error: {result.error}",
                    )
                )
            all_feedback.extend(result.feedback)

        # Filter by minimum priority and sort
        filtered = [f for f in all_feedback if f.priority <= min_priority]
        return sorted(filtered, key=lambda f: (f.priority, f.category))

    def render_report(
        self,
        feedback: list[Feedback],
        show_info: bool = False,
    ) -> None:
        """Render feedback report to console."""
        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold]SYNOLOGY GURU[/bold] - Relatório de Estado",
                border_style="blue",
            )
        )
        self.console.print()

        if not feedback:
            self.console.print("[green]Sem alertas. Tudo em ordem.[/green]")
            return

        # Group by priority
        by_priority: dict[Priority, list[Feedback]] = {}
        for item in feedback:
            if item.priority == Priority.INFO and not show_info:
                continue
            if item.priority not in by_priority:
                by_priority[item.priority] = []
            by_priority[item.priority].append(item)

        # Render each priority group
        for priority in Priority:
            if priority not in by_priority:
                continue
            if priority == Priority.INFO and not show_info:
                continue

            items = by_priority[priority]
            self.console.print(f"{priority.emoji} [bold]{priority.label}[/bold] (P{priority.value})")

            for item in items:
                self.console.print(f"  • {item}")
                if item.details:
                    self.console.print(f"    [dim]{item.details}[/dim]")

            self.console.print()

    def render_summary_table(self, results: list[AgentResult]) -> None:
        """Render summary table of agent results."""
        table = Table(title="Resumo por Agente")
        table.add_column("Agente", style="cyan")
        table.add_column("P0", justify="center", style="red")
        table.add_column("P1", justify="center", style="yellow")
        table.add_column("P2", justify="center", style="blue")
        table.add_column("P3", justify="center", style="green")
        table.add_column("Estado", justify="center")

        for result in results:
            counts = {p: 0 for p in Priority}
            for f in result.feedback:
                counts[f.priority] += 1

            status = "[red]ERRO[/red]" if result.error else "[green]OK[/green]"

            table.add_row(
                result.agent_name,
                str(counts[Priority.CRITICAL]) if counts[Priority.CRITICAL] else "-",
                str(counts[Priority.HIGH]) if counts[Priority.HIGH] else "-",
                str(counts[Priority.MEDIUM]) if counts[Priority.MEDIUM] else "-",
                str(counts[Priority.LOW]) if counts[Priority.LOW] else "-",
                status,
            )

        self.console.print(table)

    async def check_health(self, show_info: bool = False) -> list[Feedback]:
        """Run full health check and display report."""
        self.console.print("[dim]A verificar estado do NAS...[/dim]")

        results = await self.run_all_agents()
        feedback = self.aggregate_feedback(results)

        self.render_report(feedback, show_info=show_info)
        self.render_summary_table(results)

        return feedback
