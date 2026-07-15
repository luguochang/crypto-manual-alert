import type { NextAuthOptions } from "next-auth";
import type { JWT } from "next-auth/jwt";
import type { OAuthConfig } from "next-auth/providers/oauth";

import {
  listMembershipContexts,
  selectMembershipContext,
} from "@/lib/auth/membership-context";
import type { AuthContext } from "@/lib/schemas/auth-context";


interface OidcProfile {
  iss?: string;
  sub: string;
  name?: string;
  email?: string;
  picture?: string;
}

const oidcIssuer = process.env.OIDC_ISSUER;
const oidcClientId = process.env.OIDC_CLIENT_ID;
const oidcClientSecret = process.env.OIDC_CLIENT_SECRET;

const providers: OAuthConfig<OidcProfile>[] = [];
if (oidcIssuer && oidcClientId && oidcClientSecret) {
  providers.push({
    id: "oidc",
    name: "Organization SSO",
    type: "oauth",
    wellKnown: `${oidcIssuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
    clientId: oidcClientId,
    clientSecret: oidcClientSecret,
    idToken: true,
    checks: ["pkce", "state"],
    authorization: { params: { scope: "openid profile email" } },
    profile(profile) {
      return {
        id: profile.sub,
        name: profile.name ?? profile.email ?? profile.sub,
        email: profile.email ?? null,
        image: profile.picture ?? null,
      };
    },
  });
}

export const authOptions: NextAuthOptions = {
  providers,
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  secret: process.env.NEXTAUTH_SECRET,
  callbacks: {
    async jwt({ token, profile, trigger, session }) {
      const oidcProfile = profile as OidcProfile | undefined;
      if (oidcProfile) {
        if (oidcProfile.iss !== undefined && oidcProfile.iss !== oidcIssuer) {
          throw new Error("Verified OIDC issuer does not match configuration");
        }
        const identityIssuer = oidcProfile.iss ?? oidcIssuer;
        if (!identityIssuer) throw new Error("Verified OIDC issuer is required");
        token.subject = oidcProfile.sub;
        token.identityIssuer = identityIssuer;
        clearContext(token);
        try {
          const contexts = await listMembershipContexts({
            subject: oidcProfile.sub,
            identityIssuer,
          });
          if (contexts.length === 1) assignContext(token, contexts[0]);
        } catch {
          token.authContextError = "context_discovery_failed";
        }
      }

      if (trigger === "update") {
        const contextId = updateContextId(session);
        const identity = tokenIdentity(token);
        if (contextId && identity) {
          try {
            assignContext(
              token,
              await selectMembershipContext(identity, contextId),
            );
          } catch {
            token.authContextError = "context_selection_failed";
          }
        } else {
          token.authContextError = "context_selection_failed";
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) session.user.id = String(token.subject ?? token.sub ?? "");
      session.identityIssuer = stringValue(token.identityIssuer);
      session.contextId = stringValue(token.contextId);
      session.contextVersion = stringValue(token.contextVersion);
      session.tenantId = stringValue(token.tenantId);
      session.tenantName = stringValue(token.tenantName);
      session.workspaceId = stringValue(token.workspaceId);
      session.workspaceName = stringValue(token.workspaceName);
      session.roles = stringArray(token.roles);
      session.permissions = stringArray(token.permissions);
      session.authContextError = stringValue(token.authContextError);
      return session;
    },
  },
};

function assignContext(token: JWT, context: AuthContext | undefined) {
  if (!context) return;
  token.contextId = context.context_id;
  token.contextVersion = context.version;
  token.tenantId = context.tenant_id;
  token.tenantName = context.tenant_name;
  token.workspaceId = context.workspace_id;
  token.workspaceName = context.workspace_name;
  token.roles = [context.role];
  token.permissions = context.permissions;
  delete token.authContextError;
}

function clearContext(token: JWT) {
  for (const key of [
    "contextId",
    "contextVersion",
    "tenantId",
    "tenantName",
    "workspaceId",
    "workspaceName",
    "roles",
    "permissions",
    "authContextError",
  ] as const) {
    delete token[key];
  }
}

function tokenIdentity(token: JWT) {
  const subject = stringValue(token.subject ?? token.sub);
  const identityIssuer = stringValue(token.identityIssuer);
  return subject && identityIssuer ? { subject, identityIssuer } : null;
}

function updateContextId(value: unknown): string {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return "";
  const contextId = (value as Record<string, unknown>).contextId;
  return typeof contextId === "string" ? contextId : "";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : [];
}
