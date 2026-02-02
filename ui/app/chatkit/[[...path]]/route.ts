/**
 * Proxy /chatkit and /chatkit/* to the backend at runtime.
 * Uses BACKEND_URL from env (read when the request runs), so it works on Vercel
 * even when rewrites in next.config.mjs were built without the var.
 */
let backendUrl =
  process.env.BACKEND_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://127.0.0.1:8000";
if (!/^https?:\/\//i.test(backendUrl)) {
  backendUrl = `https://${backendUrl}`;
}

async function proxyToBackend(
  request: Request,
  params: Promise<{ path?: string[] }>
) {
  const { path = [] } = await params;
  const pathSegment = path.length > 0 ? "/" + path.join("/") : "";
  const url = new URL(request.url);
  const backendPath = `${backendUrl}/chatkit${pathSegment}${url.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");

  const fetchOpts: RequestInit = {
    method: request.method,
    headers,
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    fetchOpts.body = request.body;
  }

  const res = await fetch(backendPath, fetchOpts);

  const responseHeaders = new Headers(res.headers);
  responseHeaders.delete("content-encoding");

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}

export async function GET(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}

export async function POST(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}

export async function PUT(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}

export async function OPTIONS(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, context.params);
}
