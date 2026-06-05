// src/services/api.ts

const API_BASE_URL = import.meta.env.DEV ? "/api/v1" : (import.meta.env.VITE_API_URL ?? "");
console.log("API_BASE_URL:", JSON.stringify(API_BASE_URL));
export interface ApiResponse<T> {
  data: T;
  status: number;
}

export interface ApiErrorResponse {
  detail?: string;
  message?: string;
}

class ApiClient {
  constructor(private readonly baseUrl: string) {}

  private get token(): string | null {
    return localStorage.getItem("clinician_token");
  }

  setToken(token: string): void {
    localStorage.setItem("clinician_token", token);
  }

  clearToken(): void {
    localStorage.removeItem("clinician_token");
  }

  private buildUrl(endpoint: string): string {
    const cleanBase = this.baseUrl.replace(/\/+$/, "");
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    return `${cleanBase}${cleanEndpoint}`;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = this.buildUrl(endpoint);

    const headers = new Headers(options.headers);

    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }

    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.clearToken();
    }

    // ✅ Fixed — clone response so we can read it twice if needed
    if (!response.ok) {
    let message = `HTTP ${response.status}`;
    const clonedResponse = response.clone();
    try {
      const error: ApiErrorResponse = await response.json();
      message = error.detail || error.message || message;
    } catch {
      const text = await clonedResponse.text();
    if (text) message = text;
    }
    throw new Error(message);
    }
    if (
      response.status === 204 ||
      response.headers.get("content-length") === "0"
    ) {
      return { data: null as T, status: response.status };
    }

    const contentType = response.headers.get("content-type");
    if (contentType?.includes("application/json")) {
      const data = await response.json();
      return { data, status: response.status };
    }

    const text = await response.text();
    return { data: text as T, status: response.status };
  }

  async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: "GET" });
  }

  async post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: "DELETE" });
  }
}

export const api = new ApiClient(API_BASE_URL);
export default api;