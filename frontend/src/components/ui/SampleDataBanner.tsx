import { Database } from "lucide-react";
import styles from "./Banner.module.css";

export function SampleDataBanner() {
  return (
    <div role="status" className={styles.banner}>
      <Database size={16} aria-hidden="true" />
      <span>Sample data. These records are made up for trying CollectIQ; none of them are real.</span>
    </div>
  );
}
