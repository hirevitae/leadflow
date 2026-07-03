import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Sparkles, RefreshCw, Check, X, Image as ImageIcon, Send } from "lucide-react";

export default function ContentStudio() {
  const [posts, setPosts] = useState([]);
  const [topics, setTopics] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [p, t] = await Promise.all([api.get("/social/posts?status=pending"), api.get("/social/topics")]);
    setPosts(p.data); setTopics((t.data.topics || []).join(", "));
  };
  useEffect(() => { load(); }, []);

  const generate = async () => {
    setBusy(true);
    try {
      const list = topics.split(",").map((x) => x.trim()).filter(Boolean);
      await api.post("/social/topics", { topics: list });
      await api.post("/social/generate", { topics: list });
      toast.success("Drafts generated");
      load();
    } catch (e) { toast.error("Generation failed"); }
    finally { setBusy(false); }
  };

  const save = async (id, patch) => {
    await api.patch(`/social/posts/${id}`, patch);
    setPosts((ps) => ps.map((p) => p.id === id ? { ...p, ...patch } : p));
  };
  const regen = async (id) => { setBusy(true); try { await api.post(`/social/posts/${id}/regenerate`); load(); } finally { setBusy(false); } };
  const reject = async (id) => { await api.post(`/social/posts/${id}/reject`); load(); };
  const publish = async (id) => {
    try { const { data } = await api.post(`/social/posts/${id}/publish`, { targets: ["facebook", "instagram"] });
      toast.success("Published! " + JSON.stringify(data.results).slice(0, 80)); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Publish failed"); }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="font-display font-bold text-3xl tracking-tight">Content Studio</h1>
      <p className="text-sm text-zinc-500 mt-1 mb-6">AI-generated social posts with banners, queued for your approval before publishing.</p>

      <Card className="mb-6"><CardContent className="p-5 space-y-3">
        <label className="text-sm font-medium">Topics (comma-separated)</label>
        <Input value={topics} onChange={(e) => setTopics(e.target.value)}
          placeholder="SSC CGL, IBPS PO, UPSC, government jobs" data-testid="topics-input" />
        <Button onClick={generate} disabled={busy} className="bg-blue-600 hover:bg-blue-700" data-testid="generate-now-btn">
          <Sparkles className="w-4 h-4 mr-1.5" /> {busy ? "Generating…" : "Generate now"}
        </Button>
        <p className="text-xs text-zinc-500">Posts are also auto-generated hourly using Google News RSS + Claude + Nano Banana banners.</p>
      </CardContent></Card>

      {posts.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-zinc-500">No pending drafts. Click "Generate now" to create some.</CardContent></Card>
      ) : posts.map((p) => (
        <Card key={p.id} className="mb-4" data-testid={`post-${p.id}`}>
          <CardContent className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              {p.image_b64 ? (
                <img src={`data:${p.image_b64.startsWith("/9j/") ? "image/jpeg" : "image/png"};base64,${p.image_b64}`} alt="banner" className="w-full rounded-md border border-zinc-200" data-testid={`post-image-${p.id}`} />
              ) : (
                <div className="w-full aspect-[1200/630] flex items-center justify-center bg-zinc-100 rounded-md border border-zinc-200 text-zinc-400">
                  <ImageIcon className="w-8 h-8" />
                </div>
              )}
              <Input className="mt-2" defaultValue={p.banner_text}
                onBlur={(e) => save(p.id, { banner_text: e.target.value })}
                data-testid={`banner-text-${p.id}`} placeholder="Banner headline" />
            </div>
            <div className="flex flex-col">
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Topic · {p.topic}</div>
              <div className="text-xs text-zinc-500 mb-2 line-clamp-1">📰 {p.headline}</div>
              <Textarea rows={6} defaultValue={p.caption}
                onBlur={(e) => save(p.id, { caption: e.target.value })}
                data-testid={`caption-${p.id}`} className="flex-1" />
              <div className="flex flex-wrap gap-2 mt-3">
                <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => publish(p.id)} data-testid={`publish-${p.id}`}>
                  <Send className="w-4 h-4 mr-1.5" /> Approve & Publish
                </Button>
                <Button variant="outline" onClick={() => regen(p.id)} data-testid={`regen-${p.id}`}>
                  <RefreshCw className="w-4 h-4 mr-1.5" /> Regenerate
                </Button>
                <Button variant="outline" onClick={() => reject(p.id)} data-testid={`reject-${p.id}`}>
                  <X className="w-4 h-4 mr-1.5" /> Reject
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
