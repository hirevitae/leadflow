import { useEffect, useRef } from "react";
import grapesjs from "grapesjs";
import "grapesjs/dist/css/grapes.min.css";
import presetNewsletter from "grapesjs-preset-newsletter";

export const GrapesEmailBuilder = ({ value, onChange }) => {
  const ref = useRef(null);
  const editorRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const editor = grapesjs.init({
      container: ref.current,
      height: "460px",
      fromElement: false,
      storageManager: false,
      plugins: [presetNewsletter],
      pluginsOpts: { [presetNewsletter]: { modalLabelImport: "Paste HTML", inlineCss: true } },
      assetManager: { embedAsBase64: true },
    });
    editor.setComponents(value || "<mj-section><p>Start designing…</p></mj-section>");
    const emit = () => {
      try {
        const html = editor.runCommand("gjs-get-inlined-html") || (editor.getHtml() + `<style>${editor.getCss()}</style>`);
        onChange?.(html);
      } catch { onChange?.(editor.getHtml()); }
    };
    editor.on("update", emit);
    editorRef.current = editor;
    return () => { try { editor.destroy(); } catch {} editorRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="border border-zinc-200 rounded-md overflow-hidden" data-testid="grapes-builder"><div ref={ref} /></div>;
};
