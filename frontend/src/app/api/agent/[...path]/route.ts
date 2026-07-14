import { proxyAgentRequest } from "@/lib/api/agent-proxy";

interface AgentRouteContext {
  params: Promise<{ path: string[] }>;
}

async function handleAgentRequest(request: Request, context: AgentRouteContext) {
  const { path } = await context.params;
  return proxyAgentRequest(request, path);
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export {
  handleAgentRequest as GET,
  handleAgentRequest as POST,
};
