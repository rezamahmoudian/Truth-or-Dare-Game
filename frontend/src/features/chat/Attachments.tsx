import { useEffect, useRef, useState } from "react";

import { authBlob } from "@/lib/auth";
import type { Attachment } from "@/lib/types";
import { VoicePlayer } from "./VoicePlayer";

const control = "press min-h-11 rounded-field bg-surface-2 px-3 text-[12px] disabled:opacity-40";

function sizeLabel(size: number) {
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(size / 1024)} KB`;
}

export function Media({ kind, url, name }: { kind: Attachment["kind"]; url: string; name: string }) {
  if (kind === "image") return <img src={url} alt={name} className="max-h-72 max-w-full rounded-field object-contain" />;
  if (kind === "video") return <video src={url} controls playsInline preload="metadata" className="max-h-72 w-full rounded-field" />;
  if (kind === "voice" || kind === "audio") return <VoicePlayer key={url} src={url} caption={kind === "voice" ? "پیش‌نمایش وویس" : name} />;
  return null;
}

export function AttachmentView({ attachment }: { attachment: Attachment }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const blobUrl = useRef("");
  useEffect(() => () => {
    request.current?.abort();
    if (blobUrl.current) URL.revokeObjectURL(blobUrl.current);
  }, []);

  async function load() {
    if (blobUrl.current) return blobUrl.current;
    setBusy(true);
    setError("");
    const controller = new AbortController();
    request.current = controller;
    try {
      const blob = await authBlob(attachment.url, controller.signal);
      if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
      blobUrl.current = URL.createObjectURL(blob);
      setUrl(blobUrl.current);
      return blobUrl.current;
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "دریافت فایل ممکن نشد.");
      throw err;
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  const title = { image: "عکس", video: "ویدئو", voice: "پیام صوتی", audio: "فایل صوتی", file: "فایل" }[attachment.kind];
  if (attachment.kind === "voice" || attachment.kind === "audio") {
    return <VoicePlayer key={attachment.url} loadSource={load} caption={attachment.kind === "voice" ? title : attachment.name} fileSize={sizeLabel(attachment.size)} downloadName={attachment.name} />;
  }
  return <div className="flex min-w-0 flex-col gap-2">
    <span className="break-all text-[12px]">{title} · {attachment.name}</span>
    <span className="text-[11px]" dir="ltr">{sizeLabel(attachment.size)}</span>
    {!url ? <button type="button" onClick={() => void load().catch(() => undefined)} disabled={busy} className={control}>
      {busy ? "در حال دریافت…" : `دریافت ${title}`}
    </button> : <>
      <Media kind={attachment.kind} url={url} name={attachment.name} />
      <a href={url} download={attachment.name} className="min-h-10 py-2 text-[12px] underline">ذخیرهٔ فایل</a>
    </>}
    {error && <p role="alert" className="text-[12px]">{error}</p>}
  </div>;
}

