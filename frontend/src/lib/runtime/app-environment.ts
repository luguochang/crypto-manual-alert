const trustedLocalEnvironments = new Set(["development", "local", "test"]);

export function requiresAuthenticatedRuntime(
  configuredEnvironment = process.env.APP_ENVIRONMENT,
  nodeEnvironment = process.env.NODE_ENV,
): boolean {
  const configured = configuredEnvironment?.trim().toLowerCase();
  if (configured) return !trustedLocalEnvironments.has(configured);
  return nodeEnvironment !== "development" && nodeEnvironment !== "test";
}
