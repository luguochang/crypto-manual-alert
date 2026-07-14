import { generateKeyPairSync } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Session } from "next-auth";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { resolveInternalAuthorization } from "../../src/lib/auth/bff-auth";


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
      tenantId: "tenant-1",
      workspaceId: "workspace-1",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
    } satisfies Session;

    const authorization = await resolveInternalAuthorization(
      new Request("https://product.example.com/api/product/api/v2/analysis", {
        headers: { "x-tenant-id": "attacker" },
      }),
      async () => session,
    );

    expect(authorization).toMatch(/^Bearer [^.]+\.[^.]+\.[^.]+$/);
    const payload = decodePayload(authorization ?? "");
    expect(payload.tenant_id).toBe("tenant-1");
    expect(payload.workspace_id).toBe("workspace-1");
    expect(payload.sub).toBe("oidc|user-1");
    expect(payload.tenant_id).not.toBe("attacker");
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
      tenantId: "tenant-agent",
      workspaceId: "workspace-agent",
      roles: ["member"],
      permissions: ["analysis:read"],
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
      tenant_id: "tenant-agent",
      workspace_id: "workspace-agent",
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
      tenantId: "compose-tenant",
      workspaceId: "compose-workspace",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
    } satisfies Session;

    const authorization = await resolveInternalAuthorization(
      new Request("http://frontend:3001/api/product/api/v2/analysis"),
      async () => session,
    );

    expect(authorization).toMatch(/^Bearer [^.]+\.[^.]+\.[^.]+$/);
    expect(decodePayload(authorization ?? "").sub).toBe("compose-user");
  });

  it("uses an explicitly enabled deployment-controlled development identity", async () => {
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
    const resolveSession = vi.fn(async () => {
      throw new Error("OIDC is not configured in local Compose");
    });

    const authorization = await resolveInternalAuthorization(
      new Request("http://0.0.0.0:3001/api/product/api/v2/analysis"),
      resolveSession,
      { audience: "crypto-alert-agent-server" },
    );

    expect(resolveSession).not.toHaveBeenCalled();
    expect(decodePayload(authorization ?? "")).toMatchObject({
      sub: "compose-user",
      tenant_id: "compose-tenant",
      workspace_id: "compose-workspace",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
      aud: "crypto-alert-agent-server",
    });
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
