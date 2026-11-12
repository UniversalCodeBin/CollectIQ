import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, vi } from "vitest";

// Screens are split into chunks fetched on first use (src/app/router.tsx). Load them all up front, as the app did
// before the split, so a test's wait measures the screen's own behaviour and not a cold module transform.
beforeAll(async () => {
  const { BUILT_SCREENS } = await import("../src/app/router");
  await Promise.all(Object.values(BUILT_SCREENS).map((load) => load()));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});
