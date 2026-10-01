import { useTheme, type ThemeChoice } from "./ThemeContext";

const OPTIONS: { value: ThemeChoice; icon: string; label: string }[] = [
  { value: "light", icon: "☀", label: "Light theme" },
  { value: "system", icon: "◐", label: "Match system theme" },
  { value: "dark", icon: "☾", label: "Dark theme" },
];

export function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  return (
    <div className="theme-toggle" role="group" aria-label="Theme">
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={choice === o.value}
          aria-label={o.label}
          title={o.label}
          onClick={() => setChoice(o.value)}
        >
          <span aria-hidden="true">{o.icon}</span>
        </button>
      ))}
    </div>
  );
}
