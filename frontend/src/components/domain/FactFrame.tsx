import { type ReactNode, useId } from "react";
import styles from "./FactFrame.module.css";

type Props = {
  layer: "original" | "ai" | "recorded";
  children: ReactNode;
  source?: string;
  actor?: string;
  timestamp?: string;
  /** The fake AI provider's output is always labelled. */
  simulated?: boolean;
};

const HEADINGS = {
  original: "Customer wrote",
  ai: "AI interpretation (unverified)",
  recorded: "Recorded by the system",
};

/** Keeps what was said, what AI guessed and what was recorded visibly apart. */
export function FactFrame({ layer, children, source, actor, timestamp, simulated }: Props) {
  const headingId = useId();
  const provenance = [source && `Source: ${source}`, actor && `By ${actor}`, timestamp].filter(Boolean).join(" · ");
  return (
    <section aria-labelledby={headingId} className={styles.frame} data-border={layer === "ai" ? "dashed" : "solid"}>
      <h3 id={headingId} className={styles.heading}>
        {HEADINGS[layer]}
        {layer === "ai" && <span className={styles.tag}>{simulated ? "AI · Simulated, not real AI output" : "AI"}</span>}
      </h3>
      <div>{children}</div>
      {provenance && <p className={styles.provenance}>{provenance}</p>}
    </section>
  );
}
