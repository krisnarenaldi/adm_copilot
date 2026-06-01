"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { setJwt, getJwt, clearJwt, getJwtClaims, isAuthenticated } from "@/lib/auth";

interface AuthContextType {
  isAuthenticated: boolean;
  userEmail: string | null;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<{
    isAuthenticated: boolean;
    userEmail: string | null;
  }>({
    isAuthenticated: false,
    userEmail: null,
  });

  // Only check localStorage on client side after mount
  useEffect(() => {
    const token = getJwt();
    if (token) {
      const claims = getJwtClaims(token);
      if (claims) {
        setAuthState({
          isAuthenticated: true,
          userEmail: claims.sub,
        });
      }
    }
  }, []);

  const login = (token: string) => {
    setJwt(token);
    const claims = getJwtClaims(token);
    if (claims) {
      setAuthState({
        isAuthenticated: true,
        userEmail: claims.sub,
      });
    }
  };

  const logout = () => {
    clearJwt();
    setAuthState({
      isAuthenticated: false,
      userEmail: null,
    });
  };

  return (
    <AuthContext.Provider value={{ ...authState, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
