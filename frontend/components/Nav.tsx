"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getToken, logout } from "@/lib/api";
import Brand from "@/components/Brand";

export default function Nav() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    }
  }, [router]);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
        <Link href="/" aria-label="Frame Extractor home">
          <Brand />
        </Link>
        <button
          onClick={handleLogout}
          className="rounded-full border border-line px-4 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-chip"
        >
          Log out
        </button>
      </div>
    </nav>
  );
}
