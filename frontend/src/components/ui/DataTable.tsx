import type { ReactNode } from "react";
import styles from "./DataTable.module.css";

export type Column<Row> = {
  key: string;
  header: string;
  rowHeader?: boolean;
  numeric?: boolean;
  sortable?: boolean;
  /** Takes the whole card width when rows turn into cards on narrow screens. */
  wide?: boolean;
  render?: (row: Row) => ReactNode;
};

export type TableSort = { key: string; direction: "ascending" | "descending" };

type Props<Row> = {
  caption: string;
  columns: Array<Column<Row>>;
  rows: Row[];
  rowKey: (row: Row) => string;
  empty?: ReactNode;
  sort?: TableSort;
  onSort?: (key: string) => void;
};

function cellValue<Row>(column: Column<Row>, row: Row): ReactNode {
  return column.render ? column.render(row) : ((row as Record<string, ReactNode>)[column.key] ?? null);
}

/**
 * One table for every width. A container query turns rows into cards, so reading order and
 * semantics stay the same. Display changes strip table roles, so the roles are explicit.
 */
export function DataTable<Row>({ caption, columns, rows, rowKey, empty, sort, onSort }: Props<Row>) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className={styles.container}>
      <table role="table" className={styles.table}>
        <caption className={styles.caption}>{caption}</caption>
        <thead role="rowgroup" className={styles.head}>
          <tr role="row">
            {columns.map((column) => (
              <th
                key={column.key}
                role="columnheader"
                scope="col"
                data-numeric={column.numeric || undefined}
                aria-sort={sort?.key === column.key ? sort.direction : undefined}
              >
                {column.sortable && onSort ? (
                  <button type="button" className={styles.sort} onClick={() => onSort(column.key)}>
                    {column.header}
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup">
          {rows.map((row) => (
            <tr key={rowKey(row)} role="row">
              {columns.map((column) =>
                column.rowHeader ? (
                  <th key={column.key} role="rowheader" scope="row" data-label={column.header}>
                    {cellValue(column, row)}
                  </th>
                ) : (
                  <td
                    key={column.key}
                    role="cell"
                    data-label={column.header}
                    data-numeric={column.numeric || undefined}
                    data-wide={column.wide || undefined}
                  >
                    {cellValue(column, row)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
