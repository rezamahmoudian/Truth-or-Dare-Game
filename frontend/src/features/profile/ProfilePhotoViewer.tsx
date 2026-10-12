import { useEffect, useRef, useState } from "react";
import type { PublicUser } from "@/lib/types";
import { Avatar } from "@/ui/Avatar";

export function ProfilePhotoViewer({ person, onClose }: { person: PublicUser; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); previousFocus?.focus(); };
  }, []);
  return <dialog ref={dialog} className="profile-photo-dialog" aria-label={`عکس پروفایل ${person.display_name}`} onCancel={onClose} onClick={e => { const bounds = e.currentTarget.getBoundingClientRect(); if (e.target === e.currentTarget || e.clientX < bounds.left || e.clientX > bounds.right || e.clientY < bounds.top || e.clientY > bounds.bottom) onClose(); }}>
    <div className="profile-photo-view">
      <header><span>{person.display_name}</span><button type="button" onClick={onClose} aria-label="بستن عکس">✕</button></header>
      {person.avatar_url && !failed ? <img src={person.avatar_url} alt={`عکس بزرگ ${person.display_name}`} onError={() => setFailed(true)} /> : <div className="profile-photo-fallback"><Avatar avatarKey={person.avatar || "a1"} name={person.display_name} size={180} /><p>{failed ? "بارگیری عکس ممکن نشد." : "هنوز عکسی انتخاب نشده است."}</p></div>}
    </div>
  </dialog>;
}
