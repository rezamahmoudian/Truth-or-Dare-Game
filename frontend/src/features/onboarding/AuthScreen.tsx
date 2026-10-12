import { useState } from "react";
import { ApiError } from "@/lib/auth";
import { hasExistingDeviceToken } from "@/lib/deviceToken";
import { useSession } from "@/store/session";
import { Button } from "@/ui/Button";

export function AuthScreen() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const login = useSession(s => s.login);
  const register = useSession(s => s.register);
  const resumeGuest = useSession(s => s.resumeGuest);
  const isRegister = mode === "register";
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); }
    catch (e) { setError(e instanceof ApiError ? e.firstMessage || "انجام نشد؛ دوباره تلاش کن." : "ارتباط برقرار نشد؛ دوباره تلاش کن."); }
    finally { setBusy(false); }
  }
  return <main className="auth-screen" dir="rtl">
    <div className="auth-content">
      <header className="auth-brand"><span className="auth-dice" aria-hidden>🎲</span><h1>بی‌هوا</h1><p>یه بازی، یه آشنایی تازه</p></header>
      <section className="auth-card" aria-label="ورود و ثبت‌نام">
        <div className="auth-tabs" role="group" aria-label="انتخاب ورود یا ثبت‌نام">
          {([['login', 'ورود'], ['register', 'ثبت‌نام']] as const).map(([key, label]) => <button key={key} type="button" disabled={busy} aria-pressed={mode === key} onClick={() => { setMode(key); setError(""); setPassword(""); setConfirm(""); setShowPassword(false); }}>{label}</button>)}
        </div>
        <h2>{isRegister ? "هم‌بازی جدیدمون تویی؟" : "خوش برگشتی!"}</h2>
        <p className="auth-description">{isRegister ? "نام کاربری و رمزت رو بساز؛ بعد با هم پروفایلت رو کامل می‌کنیم." : "با نام کاربری و رمزت وارد شو و گفت‌وگوهات رو ادامه بده."}</p>
        <form onSubmit={e => {
          e.preventDefault();
          if (isRegister && password !== confirm) { setError("تکرار رمز عبور مطابقت ندارد."); return; }
          void run(() => isRegister ? register(username, password, confirm) : login(username, password));
        }}>
          <label htmlFor="auth-username">نام کاربری</label>
          <input id="auth-username" name="username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} dir="ltr" required minLength={isRegister ? 3 : 1} maxLength={isRegister ? 20 : 150} placeholder={isRegister ? "your_username" : "نام کاربری"} disabled={busy} />
          {isRegister && <p className="auth-field-hint">۳ تا ۲۰ کاراکتر؛ حروف انگلیسی، عدد و زیرخط.</p>}
          <label htmlFor="auth-password">رمز عبور</label>
          <div className="auth-password"><input id="auth-password" name="password" value={password} onChange={e => setPassword(e.target.value)} type={showPassword ? "text" : "password"} dir="ltr" autoComplete={isRegister ? "new-password" : "current-password"} required minLength={isRegister ? 8 : 1} maxLength={256} disabled={busy} /><button type="button" aria-label={showPassword ? "پنهان کردن رمز" : "نمایش رمز"} aria-pressed={showPassword} onClick={() => setShowPassword(v => !v)}>{showPassword ? "پنهان" : "نمایش"}</button></div>
          {isRegister && <><p className="auth-field-hint">حداقل ۸ کاراکتر؛ یک رمز غیرقابل‌حدس انتخاب کن.</p><label htmlFor="auth-confirm">تکرار رمز عبور</label><input id="auth-confirm" value={confirm} onChange={e => setConfirm(e.target.value)} type={showPassword ? "text" : "password"} dir="ltr" autoComplete="new-password" required maxLength={256} disabled={busy} /></>}
          {error && <p role="alert" className="auth-error">{error}</p>}
          <Button type="submit" busy={busy} className="mt-5">{isRegister ? "ثبت‌نام و ادامه" : "ورود به حساب"}</Button>
        </form>
        <p className="auth-switch">{isRegister ? "حساب داری؟" : "هنوز حساب نداری؟"} <button type="button" disabled={busy} onClick={() => { setMode(isRegister ? "login" : "register"); setError(""); setPassword(""); setConfirm(""); }}>{isRegister ? "وارد شو" : "ثبت‌نام کن"}</button></p>
      </section>
      {hasExistingDeviceToken() && <button type="button" disabled={busy} className="auth-guest-resume" onClick={() => void run(resumeGuest)}>ادامهٔ حساب مهمان قبلی همین مرورگر</button>}
      <p className="auth-age-note">برای بازیکن‌های ۱۸ سال به بالا</p>
    </div>
  </main>;
}
