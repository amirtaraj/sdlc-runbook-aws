// Renders any stage output from its JSON schema (RUNBOOK.md), so new stages need no UI code:
// enums -> labelled chips, strings -> paragraphs, string lists -> bullets,
// object lists -> tables, nested objects -> sub-sections.
import type { JsonSchema, StageOutput } from "../../types/run";

const label = (key: string) => key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function Cell({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== "object")) {
      return value.length > 2 || String(value.join("")).length > 40 ? (
        <ul>
          {value.map((v, i) => (
            <li key={i}>{String(v)}</li>
          ))}
        </ul>
      ) : (
        <span className="id-list">{value.join(", ") || "—"}</span>
      );
    }
    return <span>{JSON.stringify(value)}</span>;
  }
  return <>{value === "" || value == null ? "—" : String(value)}</>;
}

function Field({ name, schema, value }: { name: string; schema: JsonSchema; value: unknown }) {
  if (schema.type === "string" && schema.enum) {
    return (
      <div className="field-inline">
        <span className="field-label">{label(name)}</span>
        <span className="chip-value">{String(value).replace(/_/g, " ")}</span>
      </div>
    );
  }

  if (schema.type === "string" || schema.type === "boolean") {
    return (
      <section className="stage-section">
        <h4>{label(name)}</h4>
        {value === "" || value == null ? <p className="muted">None.</p> : <p>{String(value)}</p>}
      </section>
    );
  }

  if (schema.type === "array") {
    const items = (value as unknown[]) ?? [];
    const itemSchema = schema.items;
    return (
      <section className="stage-section">
        <h4>{label(name)}</h4>
        {!items.length ? (
          <p className="muted">None.</p>
        ) : itemSchema?.type === "object" ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(itemSchema.properties ?? {}).map((col) => (
                    <th key={col}>{label(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(items as Record<string, unknown>[]).map((row, i) => (
                  <tr key={i}>
                    {Object.keys(itemSchema.properties ?? {}).map((col) => (
                      <td key={col} className={col === "id" ? "nowrap" : undefined}>
                        <Cell value={row[col]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul>
            {items.map((item, i) => (
              <li key={i}>{String(item)}</li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  if (schema.type === "object") {
    const obj = (value as Record<string, unknown>) ?? {};
    return (
      <section className="stage-section">
        <h4>{label(name)}</h4>
        {Object.entries(schema.properties ?? {}).map(([k, sub]) => (
          <Field key={k} name={k} schema={sub} value={obj[k]} />
        ))}
      </section>
    );
  }
  return null;
}

export function StageContent({ schema, output }: { schema: JsonSchema | undefined; output: StageOutput }) {
  const props = Object.entries(schema?.properties ?? {}).filter(([k]) => k !== "refusal");
  const enums = props.filter(([, s]) => s.type === "string" && s.enum);
  const rest = props.filter(([, s]) => !(s.type === "string" && s.enum));
  return (
    <>
      {enums.length > 0 && (
        <div className="field-row">
          {enums.map(([k, s]) => (
            <Field key={k} name={k} schema={s} value={output[k]} />
          ))}
        </div>
      )}
      {rest.map(([k, s]) => (
        <Field key={k} name={k} schema={s} value={output[k]} />
      ))}
    </>
  );
}
