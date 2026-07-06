import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import GitHub from "next-auth/providers/github";

const CONTEXTA_API_URL = (process.env.CONTEXTA_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type ExtendedSession = {
  user: {
    id: string;
    email: string;
    name: string;
    image?: string | null;
    org_id: string;
    role: string;
  };
  expires: string;
};

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        try {
          const res = await fetch(`${CONTEXTA_API_URL}/v1/auth/signin`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });
          if (!res.ok) return null;
          const data = await res.json();
          return {
            id: data.account_id,
            email: data.email,
            name: data.display_name ?? data.name ?? data.email?.split("@")[0] ?? "User",
            image: data.avatar_url ?? null,
            org_id: data.organization_id,
            role: data.role ?? "member",
          };
        } catch {
          return null;
        }
      },
    }),
    ...(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET
      ? [Google({ clientId: process.env.AUTH_GOOGLE_ID, clientSecret: process.env.AUTH_GOOGLE_SECRET })]
      : []),
    ...(process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET
      ? [GitHub({ clientId: process.env.AUTH_GITHUB_ID, clientSecret: process.env.AUTH_GITHUB_SECRET })]
      : []),
  ],
  pages: {
    signIn: "/sign-in",
  },
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, user, trigger, session }) {
      if (user) {
        token.id = user.id;
        token.org_id = (user as any).org_id;
        token.role = (user as any).role;
      }
      if (trigger === "update" && session) {
        token.org_id = session.org_id ?? token.org_id;
        token.role = session.role ?? token.role;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
        (session.user as any).org_id = token.org_id as string;
        (session.user as any).role = token.role as string;
      }
      return session;
    },
  },
  trustHost: true,
});
