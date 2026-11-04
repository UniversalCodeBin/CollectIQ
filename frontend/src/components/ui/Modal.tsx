import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Button } from "./Button";
import styles from "./Modal.module.css";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  destructive?: boolean;
};

type Props = ModalProps & { placement: "centre" | "side" };

function Layer({ onClose, title, children, destructive, placement }: Omit<Props, "open">) {
  const panel = useRef<HTMLDivElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const others = [...document.body.children].filter((element) => element !== layer.current && !element.hasAttribute("inert"));
    for (const element of others) element.setAttribute("inert", "");
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const body = panel.current?.querySelector<HTMLElement>("[data-body]");
    const start =
      (destructive ? body?.querySelector<HTMLElement>("[data-cancel]") : null) ??
      body?.querySelector<HTMLElement>(FOCUSABLE) ??
      panel.current;
    start?.focus();

    return () => {
      for (const element of others) element.removeAttribute("inert");
      document.body.style.overflow = overflow;
      opener?.focus();
    };
  }, [destructive]);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panel.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div
      ref={layer}
      className={styles.scrim}
      data-placement={placement}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !destructive) onClose();
      }}
    >
      <div
        ref={panel}
        role={destructive ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={styles.panel}
        onKeyDown={onKeyDown}
      >
        <div className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          <Button variant="quiet" aria-label="Close" onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </Button>
        </div>
        <div data-body className={styles.body}>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** jsdom and older browsers lack showModal, and the drawer needs the same behaviour, so this is shared. */
export function Modal({ open, ...props }: Props) {
  return open ? <Layer {...props} /> : null;
}
