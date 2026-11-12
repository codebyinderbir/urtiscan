import type { Analysis, Health, Photo, PhotoSummary, Point } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

export const api = {
  health: () => request<Health>("/api/health"),
  listPhotos: () => request<PhotoSummary[]>("/api/photos"),
  getPhoto: (id: string) => request<Photo>(`/api/photos/${id}`),
  deletePhoto: (id: string) => request<void>(`/api/photos/${id}`, { method: "DELETE" }),
  reanalyse: (id: string) => post<Photo>(`/api/photos/${id}/reanalyse`),

  upload(file: File, region: string, takenAt: string): Promise<Photo> {
    const form = new FormData();
    form.append("file", file);
    form.append("region", region);
    if (takenAt) form.append("taken_at", new Date(takenAt).toISOString());
    return request<Photo>("/api/photos", { method: "POST", body: form });
  },

  addLesion: (aid: string, polygon: Point[]) => post<Analysis>(`/api/analyses/${aid}/lesions`, { polygon }),
  reject: (aid: string, lid: string) => post<Analysis>(`/api/analyses/${aid}/lesions/${lid}/reject`),
  restore: (aid: string, lid: string) => post<Analysis>(`/api/analyses/${aid}/lesions/${lid}/restore`),
  merge: (aid: string, ids: string[]) => post<Analysis>(`/api/analyses/${aid}/merge`, { lesion_ids: ids }),
  confirm: (aid: string) => post<Analysis>(`/api/analyses/${aid}/confirm`),
  reopen: (aid: string) => post<Analysis>(`/api/analyses/${aid}/reopen`),
  labelsUrl: (aid: string) => `/api/analyses/${aid}/labels.txt`,
};
