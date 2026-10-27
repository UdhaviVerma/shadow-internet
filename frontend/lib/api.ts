export type GetToken = () => Promise<string | null>;

export async function api<T>(path: string, token: GetToken, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const jwt = await token();
  if (jwt) headers.set("Authorization", `Bearer ${jwt}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}). Verify your domain and service configuration.`);
  }
  return response.json() as Promise<T>;
}

export async function download(path: string, token: GetToken, filename: string): Promise<void> {
  const jwt = await token();
  const response = await fetch(path, { headers: jwt ? { Authorization: `Bearer ${jwt}` } : {} });
  if (!response.ok) throw new Error(`Report export failed (${response.status})`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
