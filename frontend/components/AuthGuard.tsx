"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/providers/AuthProvider";
import { isAuthenticated } from "@/lib/auth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/");
    }
    setIsChecking(false);
  }, [router]);

  if (isChecking) {
    return null; // Or a loading spinner
  }

  if (!isAuthenticated()) {
    return null;
  }

  return <>{children}</>;
}
