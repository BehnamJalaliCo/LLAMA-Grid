export type Server = {
  id: string;
  name: string;
  private_ip: string;
  provider: string;
  status: string;
  rpc_port: number;
};

export type Model = {
  id: string;
  model_id: string;
  display_name: string;
  status: string;
  quantization?: string;
  context_length?: number;
};

export type Summary = {
  servers: number;
  healthy_servers: number;
  models: number;
  deployments: number;
  running_jobs: number;
  inference: { model: string; replicas: number; context_length?: number | null };
};

export const API_BASE = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `HTTP ${response.status}`);
  return response.json();
}
