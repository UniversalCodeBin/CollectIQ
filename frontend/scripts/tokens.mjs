// Renders src/styles/tokens.json as CSS variables and a TypeScript constant.
const kebab = (name) => name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

function flatten(value, path = []) {
  if (typeof value !== "object") return [[path.map(kebab).join("-"), value]];
  return Object.entries(value).flatMap(([key, inner]) => flatten(inner, [...path, key]));
}

export function renderCss(tokens) {
  const lines = flatten(tokens).map(([name, value]) => `  --${name}: ${value};`);
  return `/* Generated from tokens.json by scripts/gen-tokens.mjs. Do not edit. */\n:root {\n${lines.join("\n")}\n}\n`;
}

export function renderTs(tokens) {
  const body = JSON.stringify(tokens, null, 2);
  return `// Generated from tokens.json by scripts/gen-tokens.mjs. Do not edit.\nexport const tokens = ${body} as const;\n`;
}
