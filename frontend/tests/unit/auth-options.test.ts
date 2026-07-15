import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const membershipMocks = vi.hoisted(() => ({
  list: vi.fn(),
  select: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/membership-context", () => ({
  listMembershipContexts: membershipMocks.list,
  selectMembershipContext: membershipMocks.select,
}));

describe("Auth.js OIDC issuer boundary", () => {
  beforeEach(() => {
    membershipMocks.list.mockReset().mockResolvedValue([]);
    membershipMocks.select.mockReset();
  });

  afterEach(() => {
    delete process.env.OIDC_ISSUER;
    delete process.env.OIDC_CLIENT_ID;
    delete process.env.OIDC_CLIENT_SECRET;
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it.each([
    "https://attacker.example.com/realms/acme",
    "https://identity.example.com/realms/acme",
  ])("fails closed in production for non-exact issuer %s", async (profileIssuer) => {
    vi.stubEnv("NODE_ENV", "production");
    process.env.OIDC_ISSUER = "https://identity.example.com/realms/acme/";
    process.env.OIDC_CLIENT_ID = "client-id";
    process.env.OIDC_CLIENT_SECRET = "client-secret";
    const { authOptions } = await import("../../src/lib/auth/auth-options");
    const jwt = authOptions.callbacks?.jwt;
    if (!jwt) throw new Error("JWT callback is not configured");
    const profile = {
      iss: profileIssuer,
      sub: "alice-subject",
      tenant_id: "attacker-tenant",
      roles: ["admin"],
    };

    await expect(
      jwt({
        token: {},
        user: { id: "alice-subject" },
        account: null,
        profile,
        trigger: "signIn",
        isNewUser: false,
      }),
    ).rejects.toThrow("does not match configuration");
    expect(membershipMocks.list).not.toHaveBeenCalled();
  });

  it("uses only the verified issuer and subject for membership discovery", async () => {
    process.env.OIDC_ISSUER = "https://identity.example.com/realms/acme/";
    process.env.OIDC_CLIENT_ID = "client-id";
    process.env.OIDC_CLIENT_SECRET = "client-secret";
    const { authOptions } = await import("../../src/lib/auth/auth-options");
    const jwt = authOptions.callbacks?.jwt;
    if (!jwt) throw new Error("JWT callback is not configured");
    const profile = {
      iss: "https://identity.example.com/realms/acme/",
      sub: "alice-subject",
      tenant_id: "attacker-tenant",
      workspace_id: "attacker-workspace",
      roles: ["admin"],
      permissions: ["tenant:all"],
    };

    const token = await jwt({
      token: {},
      user: { id: "alice-subject" },
      account: null,
      profile,
      trigger: "signIn",
      isNewUser: false,
    });

    expect(membershipMocks.list).toHaveBeenCalledWith({
      subject: "alice-subject",
      identityIssuer: "https://identity.example.com/realms/acme/",
    });
    expect(token).toMatchObject({
      subject: "alice-subject",
      identityIssuer: "https://identity.example.com/realms/acme/",
    });
    expect(token).not.toHaveProperty("tenantId");
    expect(token).not.toHaveProperty("workspaceId");
    expect(token).not.toHaveProperty("roles");
    expect(token).not.toHaveProperty("permissions");
  });
});
