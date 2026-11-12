import { createContext, type ReactNode, useContext } from "react";
import { Link } from "react-router";
import styles from "./MetricTile.module.css";

const AsTerms = createContext(false);

/**
 * A row of headline figures on one sheet, divided by hairlines instead of being boxed one by one.
 * By default it is a list of links or figures. With `terms` it is a description list: each label is a term and each
 * figure its value, which suits facts about one record, such as an invoice's balance.
 */
export function MetricStrip({
  label,
  children,
  terms = false,
}: {
  label: string;
  children: ReactNode;
  terms?: boolean;
}) {
  const Strip = terms ? "dl" : "ul";
  return (
    <AsTerms.Provider value={terms}>
      <Strip className={styles.strip} aria-label={label}>
        {children}
      </Strip>
    </AsTerms.Provider>
  );
}

type TileProps = {
  label: string;
  /** Already formatted. Money is formatted from integer minor units before it gets here. */
  value: ReactNode;
  detail?: ReactNode;
  /** Where the figure's records are listed. The whole tile becomes the link. */
  to?: string;
};

export function MetricTile({ label, value, detail, to }: TileProps) {
  const asTerms = useContext(AsTerms);
  if (asTerms && !to) {
    return (
      <div className={`${styles.item} ${styles.tile}`}>
        <dt className={styles.label}>{label}</dt>
        <dd className={styles.value}>{value}</dd>
        {detail && <dd className={styles.detail}>{detail}</dd>}
      </div>
    );
  }
  const body = (
    <>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
      {detail && <span className={styles.detail}>{detail}</span>}
    </>
  );
  return (
    <li className={styles.item}>
      {to ? (
        <Link to={to} className={styles.tile}>
          {body}
        </Link>
      ) : (
        <div className={styles.tile}>{body}</div>
      )}
    </li>
  );
}
