import { ThemeToggle } from "../../theme/ThemeToggle";
import { ProfileMenu } from "./ProfileMenu";

interface Props {
  title: string;
  onToggleSidebar: () => void;
  onOpenMetrics: () => void;
}

export function TopBar({ title, onToggleSidebar, onOpenMetrics }: Props) {
  return (
    <header className="top-bar">
      <button type="button" className="icon-button sidebar-toggle" aria-label="Toggle run history" onClick={onToggleSidebar}>
        <span aria-hidden="true">☰</span>
      </button>
      <h1 className="top-bar-title" title={title}>
        {title}
      </h1>
      <button type="button" className="btn btn-ghost" onClick={onOpenMetrics}>
        Operations
      </button>
      <ThemeToggle />
      <ProfileMenu />
    </header>
  );
}
