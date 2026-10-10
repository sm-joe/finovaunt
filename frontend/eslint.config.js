import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Your custom rules or overrides go here
    rules: {
      "no-unused-vars": "warn",
    },
  }
);
