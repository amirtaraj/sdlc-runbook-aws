from dataclasses import dataclass

APPROVER = "Runbook.Approver"
VIEWER = "Runbook.Viewer"
ROLES = (APPROVER, VIEWER)


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    email: str
    roles: tuple[str, ...]
    auth_type: str  # mock | entra

    @property
    def actor(self) -> str:
        """Identity string written to the trace and audit logs."""
        return f"{self.auth_type}:{self.email or self.user_id}"

    def has_role(self, role: str) -> bool:
        # Approvers can do everything a viewer can.
        return role in self.roles or (role == VIEWER and APPROVER in self.roles)
