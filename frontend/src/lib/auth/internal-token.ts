import "server-only";

import { randomUUID, sign } from "node:crypto";


export interface InternalIdentity {
  subject: string;
  tenantId: string;
  workspaceId: string;
  roles: string[];
  permissions: string[];
}

export interface InternalTokenConfig {
  privateKey: string;
  keyId: string;
  issuer: string;
  audience: string;
  ttlSeconds: number;
}

export function issueInternalToken(
  identity: InternalIdentity,
  config: InternalTokenConfig,
  now: Date = new Date(),
  createTokenId: () => string = randomUUID,
): string {
  validateIdentity(identity);
  validateConfig(config);
  const issuedAt = Math.floor(now.getTime() / 1000);
  const header = encodeJson({ alg: "RS256", kid: config.keyId, typ: "JWT" });
  const payload = encodeJson({
    iss: config.issuer,
    aud: config.audience,
    sub: identity.subject,
    tenant_id: identity.tenantId,
    workspace_id: identity.workspaceId,
    roles: identity.roles,
    permissions: identity.permissions,
    jti: createTokenId(),
    iat: issuedAt,
    exp: issuedAt + config.ttlSeconds,
  });
  const signingInput = `${header}.${payload}`;
  const signature = sign(
    "RSA-SHA256",
    Buffer.from(signingInput),
    config.privateKey,
  ).toString("base64url");
  return `${signingInput}.${signature}`;
}

function validateIdentity(identity: InternalIdentity) {
  if (
    !identity.subject.trim()
    || !identity.tenantId.trim()
    || !identity.workspaceId.trim()
    || !validStrings(identity.roles)
    || !validStrings(identity.permissions)
  ) {
    throw new Error("Complete server-owned identity claims are required");
  }
}

function validateConfig(config: InternalTokenConfig) {
  if (
    !Number.isInteger(config.ttlSeconds)
    || config.ttlSeconds < 1
    || config.ttlSeconds > 60
  ) {
    throw new Error("Internal token TTL must be between 1 and 60 seconds");
  }
  if (
    !config.privateKey.trim()
    || !config.keyId.trim()
    || !config.issuer.trim()
    || !config.audience.trim()
  ) {
    throw new Error("Valid internal token configuration is required");
  }
}

function validStrings(values: string[]): boolean {
  return values.length > 0 && values.every((value) => value.trim().length > 0);
}

function encodeJson(value: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}
