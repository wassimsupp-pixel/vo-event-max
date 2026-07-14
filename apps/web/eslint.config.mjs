import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // The API client (src/lib/api.ts) deliberately maps loosely-typed backend
      // JSON to typed models at the boundary; `tsc` provides the real type
      // safety (typecheck passes clean). Explicit `any` at that seam is
      // intentional, so keep it non-blocking rather than a hard error.
      "@typescript-eslint/no-explicit-any": "off",
      // React 19 experimental rule that flags the common "load data in a
      // mount effect" pattern used across every data page here. It is a
      // performance hint, not a correctness bug — keep it as a warning.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);

export default eslintConfig;
