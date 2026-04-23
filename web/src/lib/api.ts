import { httpRequest } from "@/lib/request";

export type AccountStatus = "正常" | "异常" | "禁用";
export type DrawModel = "gpt-draw-1024x1024" | "gpt-draw-1024x1536" | "gpt-draw-1536x1024" | "gpt-image-2";

export type Account = {
  id: string;
  base_url: string;
  api_key_masked: string;
  status: AccountStatus;
  success: number;
  fail: number;
  last_used_at: string | null;
  created_at: string | null;
};

type AccountListResponse = {
  items: Account[];
  available: number;
};

type AccountMutationResponse = {
  items: Account[];
  added?: number;
  removed?: number;
  total?: number;
};

export type GeneratedImageHistoryItem = {
  image_id: string;
  file_name: string;
  content_type: string;
  created_at: string;
  expires_at: string;
  size_bytes: number;
  prompt?: string;
  requested_model?: string;
  revised_prompt?: string;
  url: string;
};

export type ReferenceImageInput = {
  id: string;
  name: string;
  data_url: string;
};

export async function login(authKey: string) {
  const normalizedAuthKey = String(authKey || "").trim();
  return httpRequest<{ ok: boolean }>("/auth/login", {
    method: "POST",
    body: {},
    headers: {
      Authorization: `Bearer ${normalizedAuthKey}`,
    },
    redirectOnUnauthorized: false,
  });
}

export async function fetchAccounts() {
  return httpRequest<AccountListResponse>("/api/accounts");
}

export async function createAccounts(upstreams: Array<{ base_url: string; api_key: string }>) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "POST",
    body: { upstreams },
  });
}

export async function deleteAccounts(ids: string[]) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "DELETE",
    body: { ids },
  });
}

export async function checkAccounts(ids: string[]) {
  return httpRequest<{
    results: Array<{ id: string; status: AccountStatus; latency_ms: number }>;
  }>("/api/accounts/check", {
    method: "POST",
    body: { ids },
  });
}

export async function generateImage(
  prompt: string,
  model: DrawModel = "gpt-draw-1024x1536",
) {
  return httpRequest<{
    created: number;
    data: Array<{ b64_json: string; revised_prompt?: string; image_id?: string; url?: string; expires_at?: string }>;
  }>(
    "/v1/images/generations",
    {
      method: "POST",
      body: {
        prompt,
        model,
        n: 1,
        response_format: "b64_json",
      },
    },
  );
}

export async function fetchGeneratedImagesHistory() {
  return httpRequest<{ items: GeneratedImageHistoryItem[] }>("/api/images/history");
}
