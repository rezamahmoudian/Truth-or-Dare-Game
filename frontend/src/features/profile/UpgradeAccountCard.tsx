import { useState } from "react";

import { ApiError, authFetch, setTokens, type Me } from "@/lib/auth";
import { useSession } from "@/store/session";
import { Button } from "@/ui/Button";

/**
 * A guest account lives entirely in one browser's storage. Clearing site data
 * or switching phones destroys it — along with every friendship and
 * conversation attached to it — and the loss is invisible until it happens.
 * This is the only way back, so it is offered plainly rather than buried.
 */
export function UpgradeAccountCard() {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setUser = useSession.setState;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const data = await authFetch<{ access: string; refresh: string; user: Me }>(
        "/auth/upgrade/",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
        },
      );
      setTokens({ access: data.access, refresh: data.refresh });
      setUser({ user: data.user });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.firstMessage ?? "ثبت انجام نشد.")
          : "ثبت انجام نشد.",
      );
    } finally {
      setBusy(false);
    }
  }

  const inputClass =
    "surface-raised min-h-12 w-full rounded-field px-4 text-[15px] outline-none placeholder:text-faint focus:border-brand/60";

  return (
    <section className="surface-card rounded-card p-4">
      <h2 className="text-[15px] font-bold">🔐 حسابت رو دائمی کن</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-muted">
        الان حسابت فقط روی همین مرورگر است. با ساختن نام کاربری و رمز، از روی
        گوشی دیگر هم می‌توانی وارد شوی.
      </p>

      {!open ? (
        <Button variant="ghost" className="mt-3" onClick={() => setOpen(true)}>
          ساختن حساب دائمی
        </Button>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="نام کاربری (انگلیسی)"
            dir="ltr"
            autoComplete="username"
            className={inputClass}
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="رمز عبور"
            dir="ltr"
            autoComplete="new-password"
            className={inputClass}
          />

          {error && <p className="text-[13px] text-bad">{error}</p>}

          <Button busy={busy} disabled={!username || !password} onClick={submit}>
            ثبت
          </Button>
        </div>
      )}
    </section>
  );
}
