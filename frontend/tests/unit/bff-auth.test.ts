import { generateKeyPairSync } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Session } from "next-auth";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import {
  resolveIdentityAuthorization,
  resolveInternalAuthorization,
} from "../../src/lib/auth/bff-auth";


describe("BFF session boundary", () => {
  let keyDirectory: string | undefined;

  afterEach(() => {
    delete process.env.APP_ENVIRONMENT;
    delete process.env.INTERNAL_JWT_PRIVATE_KEY;
    delete process.env.INTERNAL_JWT_PRIVATE_KEY_FILE;
    delete process.env.INTERNAL_JWT_KID;
    delete process.env.INTERNAL_JWT_ISSUER;
    delete process.env.INTERNAL_JWT_AUDIENCE;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ENABLED;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PROFILE;
    delete process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT;
    delete process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID;
    delete process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID;
    delete process.env.DEVELOPMENT_BOOTSTRAP_ROLES;
    delete process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS;
    if (keyDirectory) rmSync(keyDirectory, { recursive: true, force: true });
    keyDirectory = undefined;
  });

  it("returns no authorization without an authenticated session", async () => {
    const authorization = await resolveInternalAuthorization(
      new Request("https://product.example.com/api/product/api/v2/analysis"),
      async () => null,
    );

    expect(authorization).toBeNull();
  });

  it("signs only the identity stored in the server session", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "key-1";
    process.env.INTERNAL_JWT_ISSUER = "https://product.example.com";
    process.env.INTERNAL_JWT_AUDIENCE = "crypto-alert-product-api";
    const session = {
      expires: "2026-07-13T16:00:00Z",
      user: { id: "oidc|user-1", name: "User", email: "user@example.com" },
      identityIssuer: "https://identity.example.com",
      contextId: "11111111-1111-4111-8111-111111111111",
      contextVersion: "v1",
      tenantId: "tenant-1",
      tenantName: "Tenant 1",
      workspaceId: "workspace-1",
      workspaceName: "Workspace 1",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
      authContextError: "",
    } satisfies Session;

    const authorization = await resolveInternalAuthorization(
      new Request("https://product.example.com/api/product/api/v2/analysis", {
        headers: { "x-tenant-id": "attacker" },
      }),
      async () => session,
    );

    expect(authorization).toMatch(/^Bearer [^.]+\.[^.]+\.[^.]+$/);
    const payload = decodePayload(authorization ?? "");
    expect(payload.sub).toBe("oidc|user-1");
    expect(payload.identity_issuer).toBe("https://identity.example.com");
    expect(payload.context_id).toBe("11111111-1111-4111-8111-111111111111");
    expect(payload.token_use).toBe("user");
    expect(payload).not.toHaveProperty("tenant_id");
    expect(payload).not.toHaveProperty("workspace_id");
    expect(payload).not.toHaveProperty("roles");
    expect(payload).not.toHaveProperty("permissions");
  });

  it("signs a short-lived Agent token for a specified audience", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "agent-key-1";
    process.env.INTERNAL_JWT_ISSUER = "https://product.example.com";
    process.env.INTERNAL_JWT_AUDIENCE = "crypto-alert-product-api";
    const session = {
      expires: "2026-07-13T16:00:00Z",
      user: { id: "oidc|agent-user" },
      identityIssuer: "https://identity.example.com",
      contextId: "22222222-2222-4222-8222-222222222222",
      contextVersion: "v2",
      tenantId: "tenant-agent",
      tenantName: "Agent Tenant",
      workspaceId: "workspace-agent",
      workspaceName: "Agent Workspace",
      roles: ["member"],
      permissions: ["analysis:read"],
      authContextError: "",
    } satisfies Session;

    const authorization = await resolveInternalAuthorization(
      new Request("https://product.example.com/api/agent/threads/6b83a8ca-80f8-4e73-8d3e-f1fd919222b7/state"),
      async () => session,
      {
        audience: "crypto-alert-agent-server",
        allowDevelopmentBootstrap: false,
      },
    );

    const payload = decodePayload(authorization ?? "");
    expect(payload.aud).toBe("crypto-alert-agent-server");
    expect(Number(payload.exp) - Number(payload.iat)).toBe(60);
    expect(payload).toMatchObject({
      sub: "oidc|agent-user",
      identity_issuer: "https://identity.example.com",
      context_id: "22222222-2222-4222-8222-222222222222",
      token_use: "user",
    });
  });

  it("loads the signing key from a server-only file", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const privatePem = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    keyDirectory = mkdtempSync(join(tmpdir(), "bff-auth-"));
    const privateKeyFile = join(keyDirectory, "private.pem");
    writeFileSync(privateKeyFile, privatePem);
    process.env.INTERNAL_JWT_PRIVATE_KEY_FILE = privateKeyFile;
    process.env.INTERNAL_JWT_KID = "key-file-1";
    process.env.INTERNAL_JWT_ISSUER = "compose-local";
    process.env.INTERNAL_JWT_AUDIENCE = "crypto-alert-product-api";
    const session = {
      expires: "2026-07-13T16:00:00Z",
      user: { id: "compose-user" },
      identityIssuer: "https://identity.example.com",
      contextId: "33333333-3333-4333-8333-333333333333",
      contextVersion: "v3",
      tenantId: "compose-tenant",
      tenantName: "Compose Tenant",
      workspaceId: "compose-workspace",
      workspaceName: "Compose Workspace",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
      authContextError: "",
    } satisfies Session;

    const authorization = await resolveInternalAuthorization(
      new Request("http://frontend:3001/api/product/api/v2/analysis"),
      async () => session,
    );

    expect(authorization).toMatch(/^Bearer [^.]+\.[^.]+\.[^.]+$/);
    expect(decodePayload(authorization ?? "").sub).toBe("compose-user");
  });

  it("never mints a user token from deployment bootstrap authority fields", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.APP_ENVIRONMENT = "development";
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "compose-ephemeral";
    process.env.INTERNAL_JWT_ISSUER = "compose-local";
    process.env.INTERNAL_JWT_AUDIENCE = "crypto-alert-product-api";
    process.env.DEVELOPMENT_BOOTSTRAP_ENABLED = "true";
    process.env.DEVELOPMENT_BOOTSTRAP_PROFILE = "local-proof";
    process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT = "compose-user";
    process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID = "compose-tenant";
    process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID = "compose-workspace";
    process.env.DEVELOPMENT_BOOTSTRAP_ROLES = '["member"]';
    process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS = '["analysis:read","analysis:write"]';
    const resolveSession = vi.fn(async () => null);

    const authorization = await resolveInternalAuthorization(
      new Request("http://0.0.0.0:3001/api/product/api/v2/analysis"),
      resolveSession,
      { audience: "crypto-alert-agent-server" },
    );

    expect(resolveSession).toHaveBeenCalledOnce();
    expect(authorization).toBeNull();
  });

  it("issues an identity-only token before a workspace is selected", async () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "identity-key";
    process.env.INTERNAL_JWT_ISSUER = "https://product.example.com";
    const session = {
      expires: "2026-07-13T16:00:00Z",
      user: { id: "oidc|new-user" },
      identityIssuer: "https://identity.example.com",
      contextId: "",
      contextVersion: "",
      tenantId: "",
      tenantName: "",
      workspaceId: "",
      workspaceName: "",
      roles: [],
      permissions: [],
      authContextError: "",
    } satisfies Session;

    const authorization = await resolveIdentityAuthorization(
      new Request("https://product.example.com/api/product/api/v2/auth/contexts"),
      async () => session,
    );
    const payload = decodePayload(authorization ?? "");
    expect(payload).toMatchObject({
      sub: "oidc|new-user",
      identity_issuer: "https://identity.example.com",
      token_use: "identity_discovery",
      aud: "crypto-alert-identity-discovery",
    });
    expect(payload).not.toHaveProperty("context_id");
  });

  it.each(["staging", "production"])(
    "rejects a complete bootstrap identity in %s",
    async (environment) => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    process.env.APP_ENVIRONMENT = environment;
    process.env.INTERNAL_JWT_PRIVATE_KEY = privateKey
      .export({ type: "pkcs8", format: "pem" })
      .toString();
    process.env.INTERNAL_JWT_KID = "compose-ephemeral";
    process.env.INTERNAL_JWT_ISSUER = "compose-local";
    process.env.DEVELOPMENT_BOOTSTRAP_ENABLED = "true";
    process.env.DEVELOPMENT_BOOTSTRAP_PROFILE = "local-proof";
    process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT = "compose-user";
    process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID = "compose-tenant";
    process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID = "compose-workspace";
    process.env.DEVELOPMENT_BOOTSTRAP_ROLES = '["member"]';
    process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS = '["analysis:read"]';

    const resolveSession = vi.fn(async () => null);
    const authorization = await resolveInternalAuthorization(
      new Request("http://127.0.0.1:3001/api/agent/threads/6b83a8ca-80f8-4e73-8d3e-f1fd919222b7/state"),
      resolveSession,
      { audience: "crypto-alert-agent-server" },
    );

    expect(authorization).toBeNull();
    expect(resolveSession).toHaveBeenCalledOnce();
    },
  );
});


function decodePayload(authorization: string): Record<string, unknown> {
  const token = authorization.replace(/^Bearer /, "");
  const encoded = token.split(".")[1];
  if (!encoded) throw new Error("Missing JWT payload");
  return JSON.parse(Buffer.from(encoded, "base64url").toString("utf8")) as Record<string, unknown>;
}
