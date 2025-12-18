import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "./api";
import { Note } from "./api.types";

export default function App(): any {
  const [notes, setNotes] = useState<Note[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    const data = await api("notes.get") as unknown as Note[];
    setNotes(data);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e.message || e)));
  }, []);

  async function createNote() {
    setLoading(true);
    setError(null);
    try {
      await api("notes.post", {
        method: "POST",
        body: { title, body },
      });
      setTitle("");
      setBody("");
      await refresh();
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-full bg-black text-white">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">Homelab App Template</h1>
          <p className="text-white/70">
            CherryPy + Postgres + Vite PWA + shadcn/ui
          </p>
        </header>

        <section className="mb-8 rounded-lg border border-white/10 p-4">
          <h2 className="mb-3 text-lg font-medium">Create a note</h2>
          <div className="space-y-3">
            <input
              className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 outline-none focus:ring-1"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <textarea
              className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 outline-none focus:ring-1"
              placeholder="Body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
            />
            <div className="flex items-center gap-3">
              <Button onClick={createNote} disabled={loading || !title.trim()}>
                {loading ? "Saving..." : "Save"}
              </Button>
              <Button variant="outline" onClick={() => refresh()} disabled={loading}>
                Refresh
              </Button>
              {error ? <span className="text-sm text-red-400">{error}</span> : null}
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-white/10">
          <div className="border-b border-white/10 px-4 py-3">
            <h2 className="text-lg font-medium">Notes</h2>
          </div>
          <ul className="divide-y divide-white/10">
            {notes.map(n =>  (
              <li key={n.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <div className="font-medium">{n.title}</div>
                  <div className="text-xs text-white/50">
                    {new Date(n.created_at).toLocaleString()}
                  </div>
                </div>
                {n.body ? <p className="mt-1 text-sm text-white/70">{n.body}</p> : null}
              </li>
            ))}
            {notes.length === 0 ? (
              <li className="px-4 py-8 text-white/60">No notes yet.</li>
            ) : null}
          </ul>
        </section>

        <footer className="mt-8 text-xs text-white/50">
          Tip: on mobile, use “Add to Home Screen” to install this PWA.
        </footer>
      </div>
    </div>
  );
}
