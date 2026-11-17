import { useEffect, useRef, useState } from "react";
import { cropPhoto, cropRegion, type CropPosition } from "./photoCrop";

const INITIAL: CropPosition = { x: 0.5, y: 0.5, zoom: 1 };
const clamp = (value: number) => Math.max(0, Math.min(1, value));

export function ProfilePhotoCropper({ file, onConfirm, onClose }: {
  file: File; onConfirm: (file: File) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const image = useRef<HTMLImageElement>(null);
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);
  const [url, setUrl] = useState("");
  const [dimensions, setDimensions] = useState<{ width: number; height: number } | null>(null);
  const [crop, setCrop] = useState(INITIAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const source = URL.createObjectURL(file);
    setUrl(source);
    return () => URL.revokeObjectURL(source);
  }, [file]);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);

  const region = dimensions ? cropRegion(dimensions.width, dimensions.height, crop) : null;
  async function confirm() {
    if (!image.current || !dimensions || busy) return;
    setBusy(true); setError("");
    try { onConfirm(await cropPhoto(image.current, crop)); }
    catch { setError("برش عکس انجام نشد؛ دوباره تلاش کن."); }
    finally { setBusy(false); }
  }

  return <dialog ref={dialog} aria-labelledby="photo-crop-title" className="photo-crop-dialog" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="flex items-center justify-between gap-3">
      <h2 id="photo-crop-title" className="font-bold">کادر عکست رو تنظیم کن</h2>
      <button type="button" disabled={busy} onClick={onClose} aria-label="بستن برش عکس" className="size-11 rounded-full bg-surface-2">✕</button>
    </header>
    <p className="mb-4 text-xs leading-6 text-muted">عکس رو جابه‌جا کن و بزرگ‌نمایی رو تنظیم کن؛ قسمت داخل دایره در آواتارت دیده می‌شه.</p>
    <div className="photo-crop-stage" tabIndex={0} role="group" aria-label="کادر برش عکس؛ با کشیدن عکس یا کلیدهای جهت‌نما تنظیم کن"
      onKeyDown={event => {
        const steps: Record<string, [number, number]> = { ArrowLeft: [0.03, 0], ArrowRight: [-0.03, 0], ArrowUp: [0, 0.03], ArrowDown: [0, -0.03] };
        const step = steps[event.key];
        if (step && !busy) { event.preventDefault(); setCrop(current => ({ ...current, x: clamp(current.x + step[0]), y: clamp(current.y + step[1]) })); }
      }}
      onPointerDown={event => {
        if (!dimensions || busy || drag.current) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
      }}
      onPointerMove={event => {
        const previous = drag.current;
        if (!previous || previous.id !== event.pointerId || !dimensions) return;
        const dx = event.clientX - previous.x, dy = event.clientY - previous.y;
        drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
        const size = event.currentTarget.getBoundingClientRect().width;
        setCrop(current => {
          const side = cropRegion(dimensions.width, dimensions.height, current).side;
          const overflowX = (dimensions.width / side - 1) * size;
          const overflowY = (dimensions.height / side - 1) * size;
          return { ...current, x: overflowX > 0 ? clamp(current.x - dx / overflowX) : 0.5, y: overflowY > 0 ? clamp(current.y - dy / overflowY) : 0.5 };
        });
      }}
      onLostPointerCapture={() => { drag.current = null; }}
      onPointerUp={event => { if (drag.current?.id === event.pointerId) { drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId); } }}
      onPointerCancel={() => { drag.current = null; }}>
      {url && <img ref={image} src={url} alt="پیش‌نمایش برش عکس پروفایل" draggable={false}
        onLoad={event => setDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
        onError={() => { setDimensions(null); setError("این عکس قابل خواندن نیست؛ یک عکس دیگر انتخاب کن."); }}
        style={dimensions && region ? { width: `${dimensions.width / region.side * 100}%`, height: `${dimensions.height / region.side * 100}%`, left: `${-region.x / region.side * 100}%`, top: `${-region.y / region.side * 100}%` } : { visibility: "hidden" }} />}
      <span className="photo-crop-mask" aria-hidden="true" />
    </div>
    <label className="mt-4 flex items-center gap-3 text-xs text-muted">بزرگ‌نمایی
      <input type="range" min="1" max="3" step="0.01" value={crop.zoom} disabled={!dimensions || busy} dir="ltr" className="h-11 min-w-0 flex-1 accent-brand"
        onChange={event => setCrop(current => ({ ...current, zoom: Number(event.target.value) }))} />
    </label>
    <button type="button" disabled={busy} onClick={() => setCrop(INITIAL)} className="min-h-11 text-xs text-muted">بازنشانی کادر</button>
    {error && <p role="alert" className="mb-3 text-xs leading-6 text-bad">{error}</p>}
    <div className="flex gap-2">
      <button type="button" disabled={!dimensions || busy} onClick={() => void confirm()} className="min-h-11 flex-1 rounded-field bg-brand px-4 text-sm font-bold text-white disabled:opacity-50">{busy ? "در حال برش…" : "تأیید برش"}</button>
      <button type="button" disabled={busy} onClick={onClose} className="min-h-11 rounded-field bg-surface-2 px-4 text-sm">انصراف</button>
    </div>
  </dialog>;
}
