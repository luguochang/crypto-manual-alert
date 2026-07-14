import "server-only";

import { readFileSync } from "node:fs";
import { getServerSession } from "next-auth/next";
import type { Session } from "next-auth";

import { authOptions } from "@/lib/auth/auth-options";
import {
  type InternalIdentity,
  issueInternalToken,
} from "@/lib/auth/internal-token";


type SessionResolver = () => Promise<Session | null>;

interface InternalAuthorizationOptions {
  audience?: string;
  allowDevelopmentBootstrap?: boolean;
}

export async function resolveInternalAuthorization(
  _request: Request,
  resolveSession: SessionResolver = () => getServerSession(authOptions),
  options: InternalAuthorizationOptions = {},
): Promise<string | null> {
  const bootstrapIdentity = options.allowDevelopmentBootstrap === false
    ? null
    : developmentBootstrapIdentity();
  const identity = bootstrapIdentity
    ?? sessionIdentity(await resolveSession());
  if (identity === null) return null;
  return `Bearer ${issueInternalToken(
    identity,
    internalTokenConfig(options.audience),
  )}`;
}

function sessionIdentity(session: Session | null): InternalIdentity | null {
  if (
    !session?.user?.id
    || !session.tenantId
    || !session.workspaceId
    || session.roles.length === 0
    || session.permissions.length === 0
  ) {
    return null;
  }
  return {
    subject: session.user.id,
    tenantId: session.tenantId,
    workspaceId: session.workspaceId,
    roles: session.roles,
    permissions: session.permissions,
  };
}

export function isDevelopmentBootstrapRuntime(): boolean {
  return process.env.APP_ENVIRONMENT === "development"
    && process.env.DEVELOPMENT_BOOTSTRAP_ENABLED === "true"
    && process.env.DEVELOPMENT_BOOTSTRAP_PROFILE === "local-proof";
}

function developmentBootstrapIdentity(): InternalIdentity | null {
  if (
    !isDevelopmentBootstrapRuntime()
  ) {
    return null;
  }
  const roles = stringArray(process.env.DEVELOPMENT_BOOTSTRAP_ROLES);
  const permissions = stringArray(
    process.env.DEVELOPMENT_BOOTSTRAP_PERMISSIONS,
  );
  const identity = {
    subject: process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT ?? "",
    tenantId: process.env.DEVELOPMENT_BOOTSTRAP_TENANT_ID ?? "",
    workspaceId: process.env.DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID ?? "",
    roles,
    permissions,
  };
  return identity.subject && identity.tenantId && identity.workspaceId
    && roles.length > 0 && permissions.length > 0
    ? identity
    : null;
}

function stringArray(value: string | undefined): string[] {
  try {
    const parsed: unknown = JSON.parse(value ?? "");
    return Array.isArray(parsed)
      && parsed.length > 0
      && parsed.every((item) => typeof item === "string" && item.length > 0)
      ? parsed
      : [];
  } catch {
    return [];
  }
}

function internalTokenConfig(audience?: string) {
  const privateKeyFile = process.env.INTERNAL_JWT_PRIVATE_KEY_FILE;
  const privateKey = process.env.INTERNAL_JWT_PRIVATE_KEY?.replace(/\\n/g, "\n")
    ?? (privateKeyFile ? readFileSync(privateKeyFile, "utf8") : "");
  return {
    privateKey,
    keyId: process.env.INTERNAL_JWT_KID ?? "",
    issuer: process.env.INTERNAL_JWT_ISSUER ?? "",
    audience: audience
      ?? process.env.INTERNAL_JWT_AUDIENCE
      ?? "crypto-alert-product-api",
    ttlSeconds: 60,
  };
}
