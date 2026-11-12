import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Health, Photo, PhotoSummary } from "./types";
import Sidebar from "./components/Sidebar";
import UploadPanel from "./components/UploadPanel";
import ReviewView from "./components/ReviewView";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [photos, setPhotos] = useState<PhotoSummary[]>([]);
  const [current, setCurrent] = useState<Photo | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setPhotos(await api.listPhotos());
    } catch (e) {
      setBackendError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setBackendError("Cannot reach the backend on port 8000. Is uvicorn running?"));
    refreshList();
  }, [refreshList]);

  const open = async (id: string) => setCurrent(await api.getPhoto(id));

  const onUploaded = (p: Photo) => {
    setCurrent(p);
    refreshList();
  };

  const onDeleted = () => {
    setCurrent(null);
    refreshList();
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>
            ◎
          </span>
          UrtiScan
          <span className="version">Milestone 1</span>
        </div>
        <div className="disclaimer" role="note">
          Research prototype · not a medical device · do not use for diagnosis or treatment decisions
        </div>
      </header>

      {backendError && <div className="banner error">{backendError}</div>}

      <div className="layout">
        <Sidebar
          photos={photos}
          selectedId={current?.id ?? null}
          onSelect={open}
          onNew={() => setCurrent(null)}
        />
        <main className="main">
          {current ? (
            <ReviewView
              key={current.id}
              photo={current}
              health={health}
              onChanged={refreshList}
              onDeleted={onDeleted}
              onReplaced={setCurrent}
            />
          ) : (
            <UploadPanel regions={health?.regions ?? []} onUploaded={onUploaded} />
          )}
        </main>
      </div>
    </div>
  );
}
