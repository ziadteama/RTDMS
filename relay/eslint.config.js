import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules", "dist"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      "max-lines": ["error", { max: 300, skipBlankLines: true }],
      "max-lines-per-function": ["error", { max: 50, skipBlankLines: true }],
    },
  },
  { files: ["test/**"], rules: { "max-lines": ["error", { max: 400, skipBlankLines: true }], "max-lines-per-function": "off" } },
);
