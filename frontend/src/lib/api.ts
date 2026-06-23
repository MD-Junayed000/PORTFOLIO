import axios from "axios";
import { getToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_BASE_URL = API_URL;

/**
 * Coalesce a stored media URL into one the browser can fetch.
 *
 * The DB may contain one of:
 *  - an absolute URL (Cloudinary: ``https://res.cloudinary.com/...``)
 *  - a backend-relative path (legacy local uploads: ``/uploads/...``)
 *  - already an empty string
 *
 * We must NEVER prepend ``API_BASE_URL`` to an absolute URL because that
 * produces nonsense like ``https://api.example.com/https://res.cloudinary...``
 * and the browser falls back to the alt text.
 */
export function absolutizeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("/uploads/")) {
    return `${API_BASE_URL}${trimmed}`;
  }
  // Fall back to the API base so legacy data (e.g. plain "/foo.png") still
  // resolves against the backend instead of 404-ing on the Vercel origin.
  return `${API_BASE_URL}${trimmed.startsWith("/") ? "" : "/"}${trimmed}`;
}

const api = axios.create({
  baseURL: API_URL,
  // NOTE: do NOT force Content-Type here. axios must set the multipart boundary
  // automatically when the body is FormData, otherwise FastAPI receives the
  // request without the file part.
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // When uploading FormData, let the browser / axios write the Content-Type
  // header so the boundary is included.
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    if (config.headers) {
      delete (config.headers as Record<string, unknown>)["Content-Type"];
      delete (config.headers as Record<string, unknown>)["content-type"];
    }
  }
  return config;
});

export default api;
