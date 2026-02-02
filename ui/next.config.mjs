/** @type {import('next').NextConfig} */

// Backend URL: use BACKEND_URL in production (e.g. Vercel), else localhost for dev
let backendUrl =
  process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";
// Next.js rewrites require destination to start with /, http://, or https://
if (!/^https?:\/\//i.test(backendUrl)) {
  backendUrl = `https://${backendUrl}`;
}

const nextConfig = {
  devIndicators: false,
  // Proxy /chat and /chatkit to the backend (local or deployed)
  async rewrites() {
    return [
      { source: "/chat", destination: `${backendUrl}/chat` },
      { source: "/chatkit", destination: `${backendUrl}/chatkit` },
      { source: "/chatkit/:path*", destination: `${backendUrl}/chatkit/:path*` },
    ];
  },
};

export default nextConfig;
