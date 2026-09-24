import { useState } from "react";

import { ApiError } from "@/lib/auth";
import {
  currentJalaliYear,
  daysInJalaliMonth,
  faNum,
  jalaliToISO,
  JALALI_MONTHS,
} from "@/lib/dates";
import { useSession } from "@/store/session";
import { Avatar, AVATAR_KEYS } from "@/ui/Avatar";
import { Button } from "@/ui/Button";
import { ChevronIcon } from "@/ui/icons";

const MIN_AGE = 18;

/**
 * Three steps, each saved as it completes.
 *
 * Saving per step rather than all at once matters here: the account already
 * exists (the guest sign-in created it before this screen rendered), so a
 * person who drops out halfway and comes back resumes where they stopped
 * instead of starting over.
 */
export function Onboarding() {
  const user = useSession((s) => s.user);
  const updateProfile = useSession((s) => s.updateProfile);

  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [avatar, setAvatar] = useState(user?.avatar || "a1");
  const [gender, setGender] = useState<"F" | "M" | "">(user?.gender ?? "");

  const thisYear = currentJalaliYear();
  const [jy, setJy] = useState(thisYear - 25);
  const [jm, setJm] = useState(1);
  const [jd, setJd] = useState(1);

  async function save(patch: Parameters<typeof updateProfile>[0], next: number) {
    setBusy(true);
    setError(null);
    try {
      await updateProfile(patch);
      setStep(next);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.firstMessage ?? "ثبت اطلاعات انجام نشد.")
          : "ثبت اطلاعات انجام نشد.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[100dvh] flex-col">
      <ProgressBar step={step} total={3} onBack={step > 0 ? () => setStep(step - 1) : undefined} />

      <div className="flex-1 overflow-y-auto overscroll-contain px-5 py-6">
        {/* Keyed on the step so each one arrives rather than replacing the
            last in place. */}
        <div key={step} className="animate-swap-in mx-auto flex max-w-md flex-col gap-6">
          {step === 0 && (
            <StepName
              displayName={displayName}
              setDisplayName={setDisplayName}
              avatar={avatar}
              setAvatar={setAvatar}
            />
          )}

          {step === 1 && <StepGender gender={gender} setGender={setGender} />}

          {step === 3 && <Finishing />}

          {step === 2 && (
            <StepBirthDate
              jy={jy}
              jm={jm}
              jd={jd}
              setJy={setJy}
              setJm={setJm}
              setJd={setJd}
              maxYear={thisYear - MIN_AGE}
            />
          )}

          {error && (
            <p className="animate-rise rounded-field bg-bad/15 px-4 py-3 text-[13px] text-bad">
              {error}
            </p>
          )}
        </div>
      </div>

      <footer
        className="bar-blur shrink-0 border-t border-line-soft px-5 py-4"
        style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto max-w-md">
          {step === 0 && (
            <Button
              busy={busy}
              disabled={displayName.trim().length < 2}
              onClick={() => save({ display_name: displayName.trim(), avatar }, 1)}
            >
              ادامه
            </Button>
          )}

          {step === 1 && (
            <Button
              busy={busy}
              disabled={!gender}
              onClick={() => gender && save({ gender }, 2)}
            >
              ادامه
            </Button>
          )}

          {step === 2 && (
            <Button
              busy={busy}
              onClick={() => save({ birth_date: jalaliToISO(jy, jm, jd) }, 3)}
            >
              شروع
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}

/**
 * Progress, plus the way back.
 *
 * Going back matters more here than it looks: a typo in the name is otherwise
 * unfixable until the whole sign-up is over, and the first thing this screen
 * asks for is the name everyone else will see.
 */
function ProgressBar({
  step,
  total,
  onBack,
}: {
  step: number;
  total: number;
  onBack?: () => void;
}) {
  return (
    <div
      className="shrink-0 px-5 pb-2 pt-4"
      style={{ paddingTop: "max(1rem, env(safe-area-inset-top))" }}
    >
      <div className="mx-auto mb-3 flex h-8 max-w-md items-center">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="press -ms-2 grid size-8 place-items-center rounded-full text-muted"
            aria-label="مرحله‌ی قبل"
          >
            <ChevronIcon size={20} />
          </button>
        )}
        <span className="ms-auto text-[12px] text-faint">
          مرحله‌ی {faNum(step + 1)} از {faNum(total)}
        </span>
      </div>
      <div className="mx-auto flex max-w-md gap-1.5">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              i <= step ? "bg-brand" : "bg-surface-2"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Between the last save and the app deciding the account is ready.
 *
 * It is usually one frame. But the alternative — advancing to a step with no
 * content — is a blank screen with a progress bar on it, and that is what
 * somebody would be left staring at if the account ever failed to flip over.
 */
function Finishing() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <span className="animate-pulse-soft grid size-16 place-items-center rounded-full bg-surface-2 text-3xl">
        🎲
      </span>
      <p className="text-[15px] text-muted">داریم آماده‌ات می‌کنیم…</p>
    </div>
  );
}

function StepName({
  displayName,
  setDisplayName,
  avatar,
  setAvatar,
}: {
  displayName: string;
  setDisplayName: (v: string) => void;
  avatar: string;
  setAvatar: (v: string) => void;
}) {
  return (
    <>
      <Heading title="اسمت چیه؟" subtitle="همین اسم را بقیه در بازی می‌بینند." />

      <div className="flex items-center gap-3">
        <Avatar avatarKey={avatar} name={displayName} size={56} />
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={32}
          autoFocus
          placeholder="نام نمایشی"
          className="surface-raised min-h-12 flex-1 rounded-field px-4 text-[16px] outline-none placeholder:text-faint focus:border-brand/60"
        />
      </div>

      <div>
        <p className="mb-3 text-[13px] text-muted">یک آواتار انتخاب کن</p>
        <div className="grid grid-cols-6 gap-3">
          {AVATAR_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setAvatar(key)}
              className="flex items-center justify-center"
              aria-label={`آواتار ${key}`}
            >
              <Avatar
                avatarKey={key}
                name={displayName}
                size={44}
                selected={key === avatar}
              />
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function StepGender({
  gender,
  setGender,
}: {
  gender: "F" | "M" | "";
  setGender: (v: "F" | "M") => void;
}) {
  const options = [
    { value: "F" as const, label: "زن" },
    { value: "M" as const, label: "مرد" },
  ];

  return (
    <>
      <Heading
        title="جنسیتت رو انتخاب کن"
        subtitle="برای حالت‌های بازی مثل «بازی با دختر» و «بازی با پسر» لازم است."
      />

      <div className="flex flex-col gap-3">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setGender(option.value)}
            className={`press min-h-14 rounded-field border px-5 text-start text-[16px] transition ${
              gender === option.value
                ? "border-brand/60 bg-brand/15 font-bold"
                : "border-line-soft bg-surface"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Said up front rather than discovered later: the restriction is what
          makes the gender-filtered queues mean anything. */}
      <p className="surface-raised rounded-field px-4 py-3 text-[13px] leading-relaxed text-muted">
        این گزینه بعداً فقط یک‌بار قابل تغییر است، چون حالت‌های بازی بر اساس آن
        انتخاب می‌شوند.
      </p>
    </>
  );
}

function StepBirthDate({
  jy,
  jm,
  jd,
  setJy,
  setJm,
  setJd,
  maxYear,
}: {
  jy: number;
  jm: number;
  jd: number;
  setJy: (v: number) => void;
  setJm: (v: number) => void;
  setJd: (v: number) => void;
  maxYear: number;
}) {
  const years = Array.from({ length: 70 }, (_, i) => maxYear - i);
  const days = Array.from({ length: daysInJalaliMonth(jy, jm) }, (_, i) => i + 1);

  const selectClass =
    "surface-raised min-h-12 flex-1 rounded-field px-3 text-[16px] outline-none focus:border-brand/60";

  return (
    <>
      <Heading
        title="تاریخ تولدت؟"
        subtitle={`ورود به برنامه برای افراد زیر ${faNum(MIN_AGE)} سال ممکن نیست.`}
      />

      <div className="flex gap-2">
        <select
          value={jd}
          onChange={(e) => setJd(Number(e.target.value))}
          className={selectClass}
          aria-label="روز"
        >
          {days.map((d) => (
            <option key={d} value={d}>
              {faNum(d)}
            </option>
          ))}
        </select>

        <select
          value={jm}
          onChange={(e) => {
            const month = Number(e.target.value);
            setJm(month);
            // Switching from a 31-day month to Esfand can leave the day out of
            // range, which would silently roll over into the next month.
            const max = daysInJalaliMonth(jy, month);
            if (jd > max) setJd(max);
          }}
          className={`${selectClass} flex-[1.4]`}
          aria-label="ماه"
        >
          {JALALI_MONTHS.map((name, i) => (
            <option key={name} value={i + 1}>
              {name}
            </option>
          ))}
        </select>

        <select
          value={jy}
          onChange={(e) => setJy(Number(e.target.value))}
          className={selectClass}
          aria-label="سال"
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {faNum(y)}
            </option>
          ))}
        </select>
      </div>

      <p className="surface-raised rounded-field px-4 py-3 text-[13px] leading-relaxed text-muted">
        تاریخ تولد بعداً قابل تغییر نیست و به کسی نمایش داده نمی‌شود؛ فقط سن شما
        دیده می‌شود.
      </p>
    </>
  );
}

function Heading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header>
      <h1 className="text-[26px] font-extrabold leading-tight">{title}</h1>
      <p className="mt-1.5 text-[14px] leading-relaxed text-muted">{subtitle}</p>
    </header>
  );
}
