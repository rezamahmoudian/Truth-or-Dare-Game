import { useState } from "react";
import { clearTokens } from "@/lib/auth";
import { socket } from "@/lib/ws";
import { useSession } from "@/store/session";

export function AccountSwitch() {
  const guest = useSession(s => s.user?.is_guest);
  const [confirm, setConfirm] = useState(false);
  return <section className="surface-card rounded-card p-4">
    <button type="button" className="min-h-11 w-full text-start text-sm text-muted" onClick={() => setConfirm(v => !v)}>خروج / ورود به حساب دیگر</button>
    {confirm && <div className="mt-2"><p className="text-xs leading-7 text-muted">{guest ? "حسابت مهمان است. برای ورود از دستگاه دیگر، اول از بخش بالا نام کاربری و رمز بساز. روی همین مرورگر می‌توانی با گزینهٔ ادامهٔ حساب مهمان برگردی." : "از این دستگاه خارج می‌شوی؛ چت‌ها و دوستانت در حساب باقی می‌مانند."}</p>
      <div className="mt-3 flex gap-3"><button type="button" className="min-h-11 flex-1 rounded-field bg-surface-2 text-sm text-bad" onClick={() => { socket.close(); clearTokens(); try { sessionStorage.removeItem("ft.pending-search"); } catch { /* unavailable storage */ } window.location.assign("/"); }}>خروج از حساب</button><button type="button" className="min-h-11 flex-1 text-sm text-muted" onClick={() => setConfirm(false)}>انصراف</button></div>
    </div>}
  </section>;
}
