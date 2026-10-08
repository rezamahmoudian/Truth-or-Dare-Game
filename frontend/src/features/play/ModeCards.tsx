import type { MatchMode } from "@/lib/types";
import { faNum } from "@/lib/dates";
import { ChevronIcon, SparkleIcon } from "@/ui/icons";

const QUEUE_LABEL: Record<string, string> = { FAST: "هم‌بازی‌ها منتظرن", SLOW: "کمی صبر، یه رفیق تازه", EMPTY: "اولین نفر باش" };

export function HeroCard({ mode, onPick }: { mode: MatchMode; onPick: (mode: MatchMode) => void }) {
  return <button type="button" disabled={mode.remaining_today === 0} onClick={() => onPick(mode)} className="press quick-card disabled:opacity-50">
    <span className="quick-kicker">✦ بذار شانس انتخاب کنه</span>
    <h2>{mode.title}</h2>
    <p>یه هم‌بازی تازه؛<br />شاید یه رفاقت غیرمنتظره!</p>
    <span className="game-card-art" aria-hidden="true">
      <span className="mini-playing-card"><b>؟</b><small>حقیقت</small></span>
      <span className="mini-playing-card"><b>ϟ</b><small>جرئت</small></span>
      <span className="art-sparkle">✦</span>
      <span className="art-dot" />
    </span>
    <span className="quick-bottom"><span className="quick-cta">{mode.remaining_today === 0 ? 'سهمیه تمام شد' : 'بزن بریم'} <ChevronIcon size={19} /></span><span className="quick-note">✧ هم‌بازی اتفاقی</span></span>
  </button>;
}

export function ModeCard({ mode, onPick }: { mode: MatchMode; onPick: (mode: MatchMode) => void }) {
  const photo = mode.key === 'girls' ? 'girl' : mode.key === 'boys' ? 'boy' : mode.key === 'deep' ? 'challenge' : null;
  const tone = mode.key === 'girls' ? 'rose' : mode.key === 'boys' ? 'sky' : mode.key === 'deep' ? 'peach' : 'lavender';
  const soldOut = mode.remaining_today === 0;
  return <button type="button" disabled={soldOut} onClick={() => onPick(mode)}
    className={`press mode-card mode-${tone} ${mode.key === 'group' ? 'mode-wide' : ''} ${photo ? 'mode-photo-card' : ''} disabled:opacity-50`}>
    {photo ? <span className="mode-photo-frame" aria-hidden="true"><img className="mode-photo" src={`/images/modes/${photo}.jpg`} alt="" loading="lazy" /></span> : mode.key === 'group' ? <span className="group-card-art" aria-hidden="true"><i>؟</i><i>✦</i><i>ϟ</i></span> : <span className="mode-symbol" aria-hidden="true"><SparkleIcon size={28} /></span>}
    <span className="mode-copy"><span className="mode-title">{mode.title}</span><span className="mode-subtitle">{mode.subtitle}</span>
      <span className={mode.is_ai ? 'mode-status' : 'sr-only'}>{mode.is_ai ? 'شخصیت داستانی AI' : QUEUE_LABEL[mode.queue_state] ?? ''}</span>
    </span>
    <span className="mode-arrow" aria-hidden="true"><ChevronIcon size={15} /></span>
    {mode.remaining_today !== null && <span className="mode-limit">{soldOut ? 'تمام شد' : `${faNum(mode.remaining_today)} بازی باقی‌مانده`}</span>}
  </button>;
}

export function FriendsCard({ onOpen }: { onOpen: () => void }) {
  return <button type="button" onClick={onOpen} className="press mode-card mode-mint mode-photo-card">
    <span className="mode-photo-frame" aria-hidden="true"><img className="mode-photo" src="/images/modes/friends.jpg" alt="" loading="lazy" /></span>
    <span className="mode-copy"><span className="mode-title">بازی با دوستات</span><span className="mode-subtitle">جمع خودمونی شما</span><span className="sr-only">ساخت روم یا ورود با کد</span></span>
    <span className="mode-arrow" aria-hidden="true"><ChevronIcon size={15} /></span>
  </button>;
}
