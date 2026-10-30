"""Project engagement workflow helpers."""

from __future__ import annotations

from backend.app.models.project import Project, ProjectStatus

# Allowed forward transitions for the sales/delivery lifecycle.
TRANSITIONS: dict[ProjectStatus, list[ProjectStatus]] = {
    ProjectStatus.CREATED: [ProjectStatus.CRAWLING],
    ProjectStatus.CRAWLING: [
        ProjectStatus.EVIDENCE_COLLECTED,
        ProjectStatus.CREATED,
    ],
    ProjectStatus.EVIDENCE_COLLECTED: [ProjectStatus.ANALYZING],
    ProjectStatus.ANALYZING: [ProjectStatus.AWAITING_APPROVAL],
    ProjectStatus.AWAITING_APPROVAL: [
        ProjectStatus.APPROVED,
        ProjectStatus.ANALYZING,
    ],
    ProjectStatus.APPROVED: [ProjectStatus.IMPLEMENTATION],
    ProjectStatus.IMPLEMENTATION: [ProjectStatus.VERIFICATION],
    ProjectStatus.VERIFICATION: [
        ProjectStatus.COMPLETED,
        ProjectStatus.IMPLEMENTATION,
        ProjectStatus.CRAWLING,  # re-crawl to verify fixes
    ],
    ProjectStatus.COMPLETED: [ProjectStatus.CRAWLING],  # new engagement cycle
}


def can_transition(current: ProjectStatus, target: ProjectStatus) -> bool:
    if current == target:
        return True
    return target in TRANSITIONS.get(current, [])


def set_project_status(project: Project, status: ProjectStatus) -> Project:
    if not can_transition(project.status, status):
        allowed = ", ".join(s.value for s in TRANSITIONS.get(project.status, []))
        raise ValueError(
            f"Cannot move from {project.status.value} to {status.value}. "
            f"Allowed: {allowed or 'none'}"
        )
    project.status = status
    return project
