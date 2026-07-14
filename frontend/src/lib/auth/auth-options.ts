import type { NextAuthOptions } from "next-auth";
import type { OAuthConfig } from "next-auth/providers/oauth";


interface OidcProfile {
  sub: string;
  name?: string;
  email?: string;
  picture?: string;
  tenant_id?: string;
  workspace_id?: string;
  roles?: string[];
  permissions?: string[];
}

const oidcIssuer = process.env.OIDC_ISSUER?.replace(/\/$/, "");
const oidcClientId = process.env.OIDC_CLIENT_ID;
const oidcClientSecret = process.env.OIDC_CLIENT_SECRET;

const providers: OAuthConfig<OidcProfile>[] = [];
if (oidcIssuer && oidcClientId && oidcClientSecret) {
  providers.push({
    id: "oidc",
    name: "Organization SSO",
    type: "oauth",
    wellKnown: `${oidcIssuer}/.well-known/openid-configuration`,
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
    async jwt({ token, profile }) {
      const oidcProfile = profile as OidcProfile | undefined;
      if (oidcProfile) {
        token.subject = oidcProfile.sub;
        token.tenantId = oidcProfile.tenant_id;
        token.workspaceId = oidcProfile.workspace_id;
        token.roles = oidcProfile.roles ?? ["member"];
        token.permissions = oidcProfile.permissions ?? [];
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) session.user.id = String(token.subject ?? token.sub ?? "");
      session.tenantId = typeof token.tenantId === "string" ? token.tenantId : "";
      session.workspaceId = typeof token.workspaceId === "string" ? token.workspaceId : "";
      session.roles = stringArray(token.roles);
      session.permissions = stringArray(token.permissions);
      return session;
    },
  },
};

function stringArray(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : [];
}
