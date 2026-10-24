// Thin wrapper around fetch() for the FastAPI backend.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, { params, body, form } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const options = { method, headers: {} };
  if (form) {
    options.body = form;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  const data = res.headers.get("content-type")?.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    let detail = data?.detail ?? data ?? res.statusText;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");  // FastAPI validation errors
    throw new ApiError(res.status, String(detail));
  }
  return data;
}

export const api = {
  get: (path, params) => request("GET", path, { params }),
  post: (path, body, params) => request("POST", path, { body, params }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  del: (path) => request("DELETE", path),
  upload: (path, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", path, { form });
  },
  exportUrl: (path, params) => {
    const url = new URL(path, window.location.origin);
    for (const [k, v] of Object.entries(params || {})) if (v) url.searchParams.set(k, v);
    return url.toString();
  },
};
