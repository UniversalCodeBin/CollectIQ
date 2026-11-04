import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderCss, renderTs } from "./tokens.mjs";

const styles = resolve(dirname(fileURLToPath(import.meta.url)), "../src/styles");
const tokens = JSON.parse(readFileSync(resolve(styles, "tokens.json"), "utf-8"));
writeFileSync(resolve(styles, "tokens.generated.css"), renderCss(tokens));
writeFileSync(resolve(styles, "tokens.generated.ts"), renderTs(tokens));
