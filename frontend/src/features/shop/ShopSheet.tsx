import { useEffect, useId, useRef, type ReactNode } from "react";
import { ShopIcon } from "./ShopIcon";
import "./shop.css";

export function ShopSheet({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => { dialog?.close(); previous?.focus(); };
  }, []);
  return <dialog className="shop-sheet" ref={ref} aria-labelledby={titleId} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) onClose();
  }}>
    <div className="shop-sheet-handle" aria-hidden="true" />
    <header><h2 id={titleId}>{title}</h2><button type="button" className="shop-icon-button" aria-label="بستن" onClick={onClose}><ShopIcon kind="close" size={20} /></button></header>
    {children}
  </dialog>;
}
