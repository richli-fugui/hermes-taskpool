"""pp-pane Agent plugin: project-scoped task-pool tools."""

from .tools import register_tools


def register(ctx) -> None:
    register_tools(ctx)
