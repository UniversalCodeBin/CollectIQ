import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import styles from "./Menu.module.css";

type Props = {
  /** What the trigger shows. */
  trigger: ReactNode;
  /** The trigger's accessible name when its content is not enough (an avatar, an icon). */
  triggerLabel?: string;
  triggerClassName?: string;
  align?: "start" | "end";
  /** Menu items: elements with role="menuitem". Choosing one closes the menu. */
  children: ReactNode;
  /** Optional non-interactive heading inside the panel (who is signed in, for example). */
  header?: ReactNode;
};

function items(panel: HTMLElement | null): HTMLElement[] {
  return panel ? Array.from(panel.querySelectorAll<HTMLElement>('[role="menuitem"]')) : [];
}

/** A menu button: arrow keys move, Escape closes and returns focus, a click outside closes. */
export function Menu({ trigger, triggerLabel, triggerClassName, align = "end", children, header }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    items(panel.current)[0]?.focus();
    function outside(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const list = items(panel.current);
    const at = list.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      list[(at + 1) % list.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      list[(at - 1 + list.length) % list.length]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      list[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      list[list.length - 1]?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div className={styles.root} ref={root} onKeyDown={open ? onKeyDown : undefined}>
      <button
        ref={button}
        type="button"
        className={triggerClassName}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={triggerLabel}
        onClick={() => setOpen((shown) => !shown)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        {trigger}
      </button>
      {open && (
        <div
          id={id}
          ref={panel}
          role="menu"
          aria-label={triggerLabel}
          className={styles.panel}
          data-align={align}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest('[role="menuitem"]')) setOpen(false);
          }}
        >
          {header && <div className={styles.header}>{header}</div>}
          {children}
        </div>
      )}
    </div>
  );
}

export const menuItemClass = styles.item;
export const menuSeparatorClass = styles.separator;
