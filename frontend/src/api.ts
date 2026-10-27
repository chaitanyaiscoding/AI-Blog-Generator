import axios from "axios";
import { API_URL } from "./config";
import { loadUser } from "./auth";

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  // Send the Django session cookie with every request.
  withCredentials: true,
  // Echo Django's csrftoken cookie back as X-CSRFToken, which Django requires
  // on POSTs from a logged-in session.
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  withXSRFToken: true,
});

// A 401/403 can mean the session expired on the server, so re-check who is
// logged in; if nobody is, the app sends the user back to login.
api.interceptors.response.use(undefined, err => {
  const status = axios.isAxiosError(err) ? err.response?.status : undefined;
  if ((status === 401 || status === 403) && err.config?.url !== "/me/") {
    loadUser();
  }
  return Promise.reject(err);
});

// Turn an axios error into a message the UI can show.
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data;
    if (data && typeof data.detail === "string") return data.detail;
    // DRF validation errors look like {"field": ["message", ...]}; show the first one.
    if (data && typeof data === "object") {
      const first = Object.values(data).flat().find(msg => typeof msg === "string");
      if (first) return first;
    }
    if (!err.response) return `Can't reach the server at ${API_URL}. Is the backend running?`;
    return `Request failed with status ${err.response.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}
