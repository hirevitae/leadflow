import { useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Upload, Download, FileSpreadsheet, CheckCircle2, AlertCircle } from "lucide-react";

export default function BulkImportDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  const reset = () => { setFile(null); setResult(null); };

  const downloadTemplate = async () => {
    try {
      const res = await api.get("/leads/template.xlsx", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "leads_template.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Could not download template");
    }
  };

  const exportAll = async () => {
    try {
      const res = await api.get("/leads/export.xlsx", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "leads_export.xlsx"; a.click();
      URL.revokeObjectURL(url);
      toast.success("Export downloaded");
    } catch (e) {
      toast.error("Export failed");
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  const submit = async () => {
    if (!file) { toast.error("Choose a file first"); return; }
    setUploading(true); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/leads/bulk-import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
      toast.success(`Imported ${res.data.created} lead${res.data.created === 1 ? "" : "s"}`);
      onDone?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Import failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid="open-bulk-import-btn">
          <FileSpreadsheet className="w-4 h-4 mr-1.5" /> Bulk import
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[560px]" data-testid="bulk-import-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Bulk import leads</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-zinc-600">
            <Button variant="outline" size="sm" onClick={downloadTemplate} data-testid="download-template-btn">
              <Download className="w-3.5 h-3.5 mr-1.5" /> Download .xlsx template
            </Button>
            <Button variant="outline" size="sm" onClick={exportAll} data-testid="export-leads-btn">
              <Download className="w-3.5 h-3.5 mr-1.5" /> Export current leads
            </Button>
          </div>

          <div
            className="border-2 border-dashed border-zinc-300 rounded-lg p-6 text-center hover:border-blue-400 hover:bg-blue-50/30 cursor-pointer transition-colors"
            onClick={() => inputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            data-testid="dropzone"
          >
            <Upload className="w-7 h-7 mx-auto text-zinc-400 mb-2" />
            {file ? (
              <>
                <div className="font-medium text-sm text-zinc-900">{file.name}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB</div>
              </>
            ) : (
              <>
                <div className="font-medium text-sm text-zinc-900">Click to choose or drop a file here</div>
                <div className="text-xs text-zinc-500 mt-1">Supports .xlsx, .xls, .csv · Required columns: <span className="mono">name</span>, <span className="mono">phone</span></div>
              </>
            )}
            <input
              ref={inputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              data-testid="bulk-import-file-input"
            />
          </div>

          {result && (
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4 space-y-1 text-sm" data-testid="import-result">
              <div className="flex items-center gap-2 text-emerald-700 font-medium">
                <CheckCircle2 className="w-4 h-4" /> Imported {result.created} of {result.total_rows} row{result.total_rows === 1 ? "" : "s"}
              </div>
              {result.skipped > 0 && (
                <div className="text-zinc-600 ml-6">Skipped {result.skipped} row(s) — missing name or phone.</div>
              )}
              {result.errors?.length > 0 && (
                <div className="ml-6">
                  <div className="flex items-center gap-1.5 text-rose-700"><AlertCircle className="w-4 h-4" /> {result.errors.length} error(s)</div>
                  <ul className="ml-5 mt-1 text-xs text-zinc-600 list-disc">
                    {result.errors.slice(0, 5).map((e, i) => (
                      <li key={i}>Row {e.row}: {e.error}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="text-xs text-zinc-500 leading-relaxed">
            <span className="font-medium text-zinc-700">Columns supported:</span> name*, phone*, email, course, source, language (english/hindi), priority (low/medium/high), notes, stage. Unknown values fall back to safe defaults.
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => { setOpen(false); reset(); }} data-testid="close-bulk-import-btn">Close</Button>
          <Button onClick={submit} disabled={!file || uploading} className="bg-blue-600 hover:bg-blue-700" data-testid="submit-bulk-import-btn">
            {uploading ? "Importing…" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
