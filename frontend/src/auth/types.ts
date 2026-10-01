export const APPROVER = "Runbook.Approver";
export const VIEWER = "Runbook.Viewer";

export interface AuthUser {
  name: string;
  email: string;
  initials: string;
  roles: string[];
}

export const canApprove = (user: AuthUser | null) => !!user?.roles.includes(APPROVER);
