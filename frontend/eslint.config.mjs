import nextConfig from "eslint-config-next";

/**
 * eslint-config-next@16 ships a native flat-config array — no
 * @eslint/eslintrc FlatCompat shim needed (that legacy-shim path chokes on
 * this config's already-resolved plugin objects with a circular-JSON
 * error). See docs/architecture/16-repository-structure.md.
 */
const eslintConfig = [
  ...nextConfig,
  {
    // See docs/architecture/22-design-system.md §2 and CLAUDE.md rule 29 —
    // dangerouslySetInnerHTML is banned with no exceptions anywhere in this app.
    rules: {
      "react/no-danger": "error",
    },
  },
];

export default eslintConfig;
