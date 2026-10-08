import { useEffect, useRef, useState } from "react";
import { ApiError, authFetch, type Me } from "@/lib/auth";
import { useSession } from "@/store/session";
import { Avatar } from "@/ui/Avatar";

export function ProfilePhotoEditor() {
  const user = useSession(s => s.user);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  if (!user) return null;
  async function save(remove = false) {
    if (busy) return;
    setBusy(true); setError(""); setSaved(false);
    try {
      const form = new FormData();
      if (file) form.append("photo", file);
      const updated = await authFetch<Me>("/users/me/photo/", {method: remove ? "DELETE" : "POST", ...(remove ? {} : {body: form})});
      useSession.setState({user: updated});
      setFile(null); setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.firstMessage || "ذخیره نشد؛ دوباره تلاش کن." : "ارتباط برقرار نشد؛ دوباره تلاش کن.");
    } finally { setBusy(false); }
  }
  return <section className="surface-card rounded-card p-4" aria-label="عکس پروفایل">
    <div className="flex items-center gap-4">
      <button type="button" disabled={busy} onClick={() => input.current?.click()} className="press relative shrink-0 rounded-full" aria-label="انتخاب عکس پروفایل">
        <Avatar avatarKey={user.avatar || 'a1'} photoUrl={preview || user.avatar_url} name={user.display_name} size={76} glow />
        <span className="absolute -bottom-1 -end-1 grid size-7 place-items-center rounded-full border-2 border-surface bg-brand text-white" aria-hidden="true">＋</span>
      </button>
      <div className="min-w-0"><h2 className="text-sm font-bold">عکس پروفایل تو</h2><p className="mt-1 text-xs leading-6 text-muted">در پروفایل و گفتگوها نمایش داده می‌شود.</p><p className="text-[11px] text-faint">JPG، PNG یا WebP · حداکثر ۵ مگابایت</p></div>
    </div>
    <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" aria-label="فایل عکس پروفایل" onChange={e => {
      const next = e.target.files?.[0]; e.target.value = ''; if (!next) return;
      setError(''); setSaved(false);
      if (!['image/jpeg','image/png','image/webp'].includes(next.type) || next.size > 5 * 1024 * 1024 || !next.size) { setError('یک عکس JPG، PNG یا WebP با حجم حداکثر ۵ مگابایت انتخاب کن.'); return; }
      setFile(next);
    }} />
    {file && <p className="mt-3 text-xs text-muted">پیش‌نمایش برش مربعی از مرکز عکس؛ برای اعمال، ذخیره را بزن.</p>}
    <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" disabled={busy} onClick={() => file ? void save() : input.current?.click()} className="press min-h-11 rounded-field bg-brand px-4 text-sm font-bold text-white disabled:opacity-50">{busy ? 'در حال ذخیره…' : file ? 'ذخیره عکس' : 'انتخاب عکس'}</button>
      {file ? <button type="button" disabled={busy} onClick={() => {setFile(null); setError('');}} className="min-h-11 rounded-field bg-surface-2 px-4 text-sm">انصراف</button> : user.avatar_url && <button type="button" disabled={busy} onClick={() => void save(true)} className="min-h-11 rounded-field px-4 text-sm text-bad">حذف عکس</button>}
    </div>
    {error && <p role="alert" className="mt-2 text-xs leading-6 text-bad">{error}</p>}
    {saved && <p role="status" className="mt-2 text-xs text-muted">عکس پروفایل به‌روز شد.</p>}
  </section>;
}
