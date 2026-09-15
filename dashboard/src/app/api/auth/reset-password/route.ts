import { contextaFetch } from "@/lib/auth-helpers";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const { email, current_password, new_password } = payload;

    if (!email || !current_password || !new_password) {
      return Response.json({ detail: "All fields are required." }, { status: 400 });
    }
    if (new_password.length < 8) {
      return Response.json({ detail: "New password must be at least 8 characters." }, { status: 400 });
    }
    if (new_password === current_password) {
      return Response.json({ detail: "New password must be different from current password." }, { status: 400 });
    }

    const res = await contextaFetch("/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        email,
        current_password,
        new_password,
      }),
    });

    if (!res.ok) {
      let detail = "Failed to update master password.";
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        const text = await res.text();
        if (text) detail = text;
      }
      return Response.json({ detail }, { status: res.status });
    }

    const data = await res.json();
    return Response.json(data);
  } catch (err: any) {
    return Response.json(
      { detail: err?.message || "Failed to communicate with Contexta backend." },
      { status: 500 }
    );
  }
}
