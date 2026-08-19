export async function api(path, opt = {}) {
  const r = await fetch(path, { credentials: "include", ...opt });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) {
    if (!path.startsWith("/auth/login")) window.location.href = "/login";
    const err = new Error("session");
    err.status = 401;
    throw err;
  }
  if (!r.ok) throw new Error(data.detail || data.reason || r.status);
  return data;
}
