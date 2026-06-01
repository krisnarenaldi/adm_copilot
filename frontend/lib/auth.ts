// lib/auth.ts - JWT storage and verification utilities

const JWT_KEY = "adm_copilot_jwt";

// Check if we're in a browser environment
const isBrowser = typeof window !== "undefined";

export interface JwtClaims {
  sub: string; // user email
  exp: number; // Unix timestamp (seconds)
  iat: number;
}

/**
 * Store JWT in localStorage.
 */
export function setJwt(token: string): void {
  if (isBrowser) {
    localStorage.setItem(JWT_KEY, token);
  }
}

/**
 * Retrieve JWT from localStorage.
 */
export function getJwt(): string | null {
  if (isBrowser) {
    return localStorage.getItem(JWT_KEY);
  }
  return null;
}

/**
 * Clear JWT from localStorage.
 */
export function clearJwt(): void {
  if (isBrowser) {
    localStorage.removeItem(JWT_KEY);
  }
}

/**
 * Parse JWT and return claims, or null if invalid/expired.
 */
export function getJwtClaims(token: string): JwtClaims | null {
  try {
    const payloadBase64 = token.split(".")[1];
    if (!payloadBase64) return null;
    const payloadJson = atob(payloadBase64);
    const claims: JwtClaims = JSON.parse(payloadJson);
    if (isBrowser) {
      const now = Date.now() / 1000; // in seconds
      if (claims.exp < now) {
        clearJwt();
        return null;
      }
    }
    return claims;
  } catch {
    return null;
  }
}

/**
 * Check if user is authenticated (has valid JWT).
 */
export function isAuthenticated(): boolean {
  if (!isBrowser) return false;
  const token = getJwt();
  if (!token) return false;
  const claims = getJwtClaims(token);
  return claims !== null;
}
