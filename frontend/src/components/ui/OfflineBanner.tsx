import { useSyncExternalStore } from "react";
import { WifiOff } from "lucide-react";
import styles from "./Banner.module.css";

function subscribe(listener: () => void) {
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

export function OfflineBanner() {
  const online = useSyncExternalStore(subscribe, () => window.navigator.onLine);
  if (online) return null;
  return (
    <div role="status" className={styles.banner}>
      <WifiOff size={16} aria-hidden="true" />
      <span>You're offline. What's on screen may be out of date, and changes can't be saved until the connection returns.</span>
    </div>
  );
}
