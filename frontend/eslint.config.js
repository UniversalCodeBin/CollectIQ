import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";
import noRawHex from "./eslint-rules/no-raw-hex.js";

export default tseslint.config(
  { ignores: ["dist/**", "src/lib/api-types.ts", "playwright-report/**", "test-results/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/styles/tokens.generated.ts"],
    plugins: { collectiq: { rules: { "no-raw-hex": noRawHex } } },
    rules: { "collectiq/no-raw-hex": "error" },
  },
  {
    files: ["*.config.{js,ts}", "eslint-rules/**/*.js"],
    languageOptions: { globals: { ...globals.node } },
  },
);
