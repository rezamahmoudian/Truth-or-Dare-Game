import { useState } from "react";
import { clearTokens } from "@/lib/auth";
import { socket } from "@/lib/ws";
import { useSession } from "@/store/session";
import { ChevronIcon, KeyIcon } from "@/ui/icons";

export function AccountSwitch() {
  const guest = useSession(s => s.user?.is_guest);
  const [confirm, setConfirm] = useState(false);
  return <section className="surface-card profile-option rounded-card p-4">
    <button type="button" className="profile-option-toggle" aria-expanded={confirm} onClick={() => setConfirm(v => !v)}><span className="profile-option-icon profile-option-icon-muted"><KeyIcon size={21} /></span><span className="profile-option-label"><strong>مدیریت حساب</strong><small>خروج یا ورود به حساب دیگر</small></span><ChevronIcon size={17} className={confirm ? "profile-chevron-open" : ""} /></button>
    {confirm && <div className="mt-2"><p className="text-xs leading-7 text-muted">{guest ? "حسابت مهمان است. برای ورود از دستگاه دیگر، اول از بخش بالا نام کاربری و رمز بساز. روی همین مرورگر می‌توانی با گزینهٔ ادامهٔ حساب مهمان برگردی." : "از این دستگاه خارج می‌شوی؛ چت‌ها و دوستانت در حساب باقی می‌مانند."}</p>
      <div className="mt-3 flex gap-3"><button type="button" className="min-h-11 flex-1 rounded-field bg-surface-2 text-sm text-bad" onClick={() => { socket.close(); clearTokens(); try { sessionStorage.removeItem("ft.pending-search"); } catch { /* unavailable storage */ } window.location.assign("/"); }}>خروج از حساب</button><button type="button" className="min-h-11 flex-1 text-sm text-muted" onClick={() => setConfirm(false)}>انصراف</button></div>
    </div>}
  </section>;
}
