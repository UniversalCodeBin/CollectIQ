// Colours come from design tokens. A raw hex value in a component is how a palette drifts.
// `#1042` in "Invoice #1042" stays legal: a colour here is a hex run of 3, 4, 6 or 8 digits
// holding at least one letter, or sitting where CSS would read it as a colour.
const HEX = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-zA-Z_-])/g;
const HAS_LETTER = /[a-fA-F]/;
const SIX_OR_EIGHT = /^#(?:.{6}|.{8})$/;

export function findRawHex(text) {
  return (text.match(HEX) ?? []).filter((value) => HAS_LETTER.test(value) || SIX_OR_EIGHT.test(value));
}

export default {
  meta: {
    type: "problem",
    docs: { description: "Disallow raw hex colours outside the generated tokens" },
    messages: { rawHex: "Use a design token instead of the raw colour {{value}}." },
    schema: [],
  },
  create(context) {
    function check(node, text) {
      for (const value of findRawHex(text)) {
        context.report({ node, messageId: "rawHex", data: { value } });
      }
    }
    return {
      Literal(node) {
        if (typeof node.value === "string") check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
      JSXText(node) {
        check(node, node.value);
      },
    };
  },
};
