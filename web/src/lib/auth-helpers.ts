import { cache } from "react";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

export type SessionUser = {
  id: string;
  email: string;
  name: string;
  image?: string | null;
  org_id: string;
  role: string;
};

export type TypedSession = {
  user: SessionUser;
  expires: string;
};

const _uncachedGetSession = async (): Promise<TypedSession | null> => {
  const session = await auth();
  if (!session?.user?.email) return null;
  return {
    user: {
      id: session.user.id as string,
      email: session.user.email as string,
      name: session.user.name as string,
      image: session.user.image as string | null | undefined,
      org_id: (session.user as any).org_id as string,
      role: (session.user as any).role as string,
    },
    expires: session.expires,
  } as TypedSession;
};

export const getSession = cache(_uncachedGetSession);

export async function requireSession(): Promise<TypedSession> {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  return session;
}

const CONTEXTA_API_BASE = (process.env.CONTEXTA_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const FETCH_TIMEOUT_MS = 15000;

export async function contextaFetch(path: string, options?: RequestInit): Promise<Response> {
  const session = await getSession();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (session?.user) {
    headers["X-User-Id"] = session.user.id;
    headers["X-Org-Id"] = session.user.org_id;
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(`${CONTEXTA_API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
      next: { revalidate: 30 },
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
