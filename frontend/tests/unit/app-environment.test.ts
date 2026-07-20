import { describe, expect, it } from "vitest";

import { requiresAuthenticatedRuntime } from "../../src/lib/runtime/app-environment";


describe("application authentication environment", () => {
  it.each(["development", "local", "test", " DEVELOPMENT "])(
    "uses the isolated local shell for %s",
    (environment) => {
      expect(requiresAuthenticatedRuntime(environment, "production")).toBe(false);
    },
  );

  it.each(["staging", "production", "preview", "unknown"])(
    "requires Auth.js for configured environment %s",
    (environment) => {
      expect(requiresAuthenticatedRuntime(environment, "development")).toBe(true);
    },
  );

  it("fails closed when a production build omits APP_ENVIRONMENT", () => {
    expect(requiresAuthenticatedRuntime(undefined, "production")).toBe(true);
  });

  it.each(["development", "test"] as const)(
    "uses the local shell only for an explicit local NODE_ENV fallback of %s",
    (nodeEnvironment) => {
      expect(requiresAuthenticatedRuntime(undefined, nodeEnvironment)).toBe(false);
    },
  );
});
