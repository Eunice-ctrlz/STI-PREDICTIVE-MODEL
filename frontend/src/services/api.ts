// src/services/api.ts

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ApiResponse<T> {
  data: T;
  status: number;
}

interface ApiError {
  detail: string;
  status: number;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null;

  constructor(baseUrl: string) {
    // Remove trailing slash to avoid double slashes when concatenating
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.token = localStorage.getItem('clinician_token');
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('clinician_token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('clinician_token');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<<ApiResponse<T>> {
    // Ensure endpoint starts with /
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${this.baseUrl}${cleanEndpoint}`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers as Record<string, string>,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return { data, status: response.status };
  }

  async get<T>(endpoint: string): Promise<<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, body: unknown): Promise<<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async put<T>(endpoint: string, body: unknown): Promise<<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }
}

export const api = new ApiClient(API_BASE_URL);