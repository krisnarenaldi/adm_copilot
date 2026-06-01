// lib/api.ts - Typed API client

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Airline {
  code: string;
  name: string;
}

export interface AuditResponse {
  verdict: "VALID DISPUTE FOUND" | "VALID ADM / NO DISPUTE";
  analysis: string;
  dispute_draft: string;
}

export async function login(request: LoginRequest): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(data.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function getAirlines(): Promise<Airline[]> {
  const res = await fetch(`${API_BASE_URL}/airlines`);
  if (!res.ok) {
    throw new Error("Failed to fetch airlines");
  }
  return res.json();
}

export async function submitAudit(
  file: File,
  airlineCode: string,
  jwt: string
): Promise<AuditResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("airline_code", airlineCode);

  const res = await fetch(`${API_BASE_URL}/audit`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jwt}`,
    },
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(data.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function uploadFareRules(
  file: File,
  airlineCode: string,
  jwt: string
): Promise<void> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("airline_code", airlineCode);

  const res = await fetch(`${API_BASE_URL}/fare-rules`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jwt}`,
    },
    body: formData,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
}
