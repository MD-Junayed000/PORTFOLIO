import axios from "axios";
import { getToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_BASE_URL = API_URL;

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
