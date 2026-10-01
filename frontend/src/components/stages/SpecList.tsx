// Per-item stage output (e.g. one specification per task): an expandable entry per item,
// each rendered generically from the item schema in RUNBOOK.md.
import type { JsonSchema, StageOutput } from "../../types/run";
import { StageContent } from "./StageContent";

interface Props {
  items: StageOutput[];
  itemSchema: JsonSchema | undefined;
}

function count(item: StageOutput, key: string): number {
  return Array.isArray(item[key]) ? (item[key] as unknown[]).length : 0;
}

export function SpecList({ items, itemSchema }: Props) {
  if (!items.length) return <p className="muted">None.</p>;
  return (
    <div className="spec-list">
      {items.map((item, i) => (
        <details key={String(item.task_id ?? i)} className="spec-item" open={items.length === 1}>
          <summary>
            <span className="spec-id">{String(item.task_id ?? `#${i + 1}`)}</span>
            <span className="spec-title">{String(item.title ?? "")}</span>
            <span className="spec-meta muted">
              {count(item, "files")} files · {count(item, "interfaces")} interfaces · {count(item, "test_cases")} tests
            </span>
          </summary>
          <div className="spec-body">
            <StageContent schema={itemSchema} output={item} />
          </div>
        </details>
      ))}
    </div>
  );
}
