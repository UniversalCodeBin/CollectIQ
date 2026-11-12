import { Link, NavLink } from "react-router";
import styles from "./Tabs.module.css";

export type TabItem = {
  to: string;
  label: string;
  /** Set when the address alone cannot tell which tab is open, for example tabs that differ only by a query string. */
  current?: boolean;
  /** A count shown after the label. It is part of the link's name, so a screen reader hears "Unmatched 3". */
  count?: number;
};

function TabText({ item }: { item: TabItem }) {
  if (item.count === undefined) return <>{item.label}</>;
  return (
    <>
      <span>{item.label}</span> <span className={styles.count}>{item.count}</span>
    </>
  );
}

/** Views of one screen. They are links, so each view has its own address and the back button works. */
export function Tabs({ label, items }: { label: string; items: TabItem[] }) {
  return (
    <nav aria-label={label} className={styles.tabs}>
      {items.map((item) =>
        item.current === undefined ? (
          <NavLink key={item.to} to={item.to} className={styles.tab}>
            <TabText item={item} />
          </NavLink>
        ) : (
          <Link key={item.to} to={item.to} className={styles.tab} aria-current={item.current ? "page" : undefined}>
            <TabText item={item} />
          </Link>
        ),
      )}
    </nav>
  );
}
