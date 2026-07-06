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

export async function getSession(): Promise<TypedSession | null> {
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
}

export async function requireSession(): Promise<TypedSession> {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  return session;
}

export async function contextaFetch(path: string, options?: RequestInit): Promise<Response> {
  const session = await getSession();
  const baseUrl = (process.env.CONTEXTA_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (session?.user) {
    headers["X-User-Id"] = session.user.id;
    headers["X-Org-Id"] = session.user.org_id;
  }
  return fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
}
