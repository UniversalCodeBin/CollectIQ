import { useState } from "react";
import { Link } from "react-router";
import { formatMinor } from "../../lib/format";
import styles from "./AgingBar.module.css";

export type AgingPart = {
  key: string;
  label: string;
  amountMinor: number;
  count: number;
  /** Where this bucket's invoices are listed. */
  to?: string;
};

/** Whole-number percentage of a total, for display only. No money figure is derived from it. */
function share(part: number, total: number): string {
  if (total <= 0) return "0%";
  const tenths = Math.round((part * 1000) / total);
  if (tenths === 0 && part > 0) return "under 0.1%";
  return `${Math.trunc(tenths / 10)}${tenths % 10 ? `.${tenths % 10}` : ""}%`;
}

/**
 * Outstanding amounts by how long past due they are: one thin bar split into ordered parts, over a table of the
 * same figures. The shade deepens with age; the table carries every number, so nothing depends on the shade.
 */
export function AgingBar({ parts, currency, caption }: { parts: AgingPart[]; currency: string; caption: string }) {
  const [active, setActive] = useState<string | null>(null);
  const total = parts.reduce((sum, part) => sum + part.amountMinor, 0);
  const summary = parts
    .filter((part) => part.amountMinor > 0)
    .map((part) => `${part.label} ${formatMinor(part.amountMinor, currency)} (${share(part.amountMinor, total)})`)
    .join(", ");

  return (
    <div className={styles.aging}>
      {total > 0 && (
        <div className={styles.bar} role="img" aria-label={`${caption}. ${summary}.`}>
          {parts.map((part, index) =>
            part.amountMinor > 0 ? (
              <span
                key={part.key}
                className={styles.segment}
                data-step={index + 1}
                data-dim={active !== null && active !== part.key ? "" : undefined}
                style={{ flexGrow: part.amountMinor }}
                title={`${part.label}: ${formatMinor(part.amountMinor, currency)}, ${share(part.amountMinor, total)}`}
                onMouseEnter={() => setActive(part.key)}
                onMouseLeave={() => setActive(null)}
              />
            ) : null,
          )}
        </div>
      )}
      <table className={styles.table}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Due</th>
            <th scope="col" className={styles.num}>
              Invoices
            </th>
            <th scope="col" className={styles.num}>
              Outstanding
            </th>
            <th scope="col" className={styles.num}>
              Share
            </th>
          </tr>
        </thead>
        <tbody>
          {parts.map((part, index) => (
            <tr
              key={part.key}
              data-active={active === part.key ? "" : undefined}
              onMouseEnter={() => setActive(part.key)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(part.key)}
              onBlur={() => setActive(null)}
            >
              <th scope="row">
                <span className={styles.swatch} data-step={index + 1} aria-hidden="true" />
                {part.to && part.count > 0 ? <Link to={part.to}>{part.label}</Link> : part.label}
              </th>
              <td className={styles.num}>{part.count}</td>
              <td className={styles.num}>{formatMinor(part.amountMinor, currency)}</td>
              <td className={styles.num}>{share(part.amountMinor, total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
