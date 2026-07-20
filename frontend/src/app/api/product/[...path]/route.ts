import { proxyProductRequest } from "@/lib/api/product-proxy";

interface ProductRouteContext {
  params: Promise<{ path: string[] }>;
}

async function handleProductRequest(request: Request, context: ProductRouteContext) {
  const { path } = await context.params;
  return proxyProductRequest(request, path);
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export {
  handleProductRequest as GET,
  handleProductRequest as PATCH,
  handleProductRequest as POST,
  handleProductRequest as PUT,
  handleProductRequest as DELETE,
};
