export async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = err.detail;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}
