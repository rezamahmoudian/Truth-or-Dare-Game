import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/lib/auth";
import { useSession } from "@/store/session";
import { Button } from "@/ui/Button";

export function ProfileDetailsEditor() {
  const user = useSession(s => s.user);
  const update = useSession(s => s.updateProfile);
  const [name, setName] = useState(user?.display_name ?? "");
  const [city, setCity] = useState(user?.city ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [interests, setInterests] = useState((user?.interests ?? []).join("، "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  if (!user) return null;
  return <form className="surface-card profile-details-editor rounded-card p-4" onChange={() => setSaved(false)} onSubmit={async e => {
    e.preventDefault(); if (busy) return;
    const items = [...new Set(interests.split(/[،,\n]/).map(item => item.trim()).filter(Boolean))];
    if (items.length > 10 || items.some(item => item.length > 24)) { setError("حداکثر ۱۰ علاقه بنویس؛ هرکدام تا ۲۴ حرف."); return; }
    setBusy(true); setError(""); setSaved(false);
    try { await update({ display_name: name.trim(), city: city.trim(), bio: bio.trim(), interests: items }); setSaved(true); }
    catch (e) { setError(e instanceof ApiError ? e.firstMessage || "ذخیره نشد." : "ارتباط برقرار نشد؛ دوباره تلاش کن."); }
    finally { setBusy(false); }
  }}>
    <div className="mb-4 flex items-center justify-between gap-2"><h2 className="font-bold">پروفایل من</h2><Link to={`/people/${user.id}`} className="text-xs text-brand-soft">دیدن پروفایل عمومی ←</Link></div>
    <label>نام نمایشی<input value={name} required minLength={2} maxLength={32} onChange={e => setName(e.target.value)} /></label>
    <label>شهر <span>اختیاری</span><input value={city} maxLength={64} placeholder="مثلاً شیراز" onChange={e => setCity(e.target.value)} /></label>
    <label>بیو<textarea value={bio} maxLength={160} rows={3} placeholder="یه کم از خودت بگو…" onChange={e => setBio(e.target.value)} /></label>
    <label>علایق<input value={interests} maxLength={270} placeholder="موسیقی، سفر، فیلم، بازی…" onChange={e => setInterests(e.target.value)} /></label>
    <p className="mb-4 text-xs leading-6 text-muted">علایق را با ویرگول جدا کن؛ تا ۱۰ مورد. این اطلاعات در پروفایل عمومی نمایش داده می‌شوند.</p>
    <Button type="submit" busy={busy}>ذخیرهٔ اطلاعات</Button>
    {error && <p role="alert" className="mt-3 text-sm text-bad">{error}</p>}
    {saved && <p role="status" className="mt-3 text-sm text-ok">اطلاعات پروفایل ذخیره شد.</p>}
  </form>;
}
