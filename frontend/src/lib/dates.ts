import { toGregorian, toJalaali } from "jalaali-js";

export const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export const faNum = (value: number | string): string =>
  String(value).replace(/\d/g, (d) => FA_DIGITS[Number(d)] ?? d);

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

/**
 * Birth dates are collected in the Jalali calendar and converted here, because
 * an Iranian user asked for their birth date in the Gregorian calendar will
 * either guess or enter the Jalali numbers into a Gregorian field — and the
 * second failure is silent, producing an age that is ~621 years wrong and an
 * age gate that no longer means anything.
 *
 * Returns the ISO date the API expects.
 */
export function jalaliToISO(jy: number, jm: number, jd: number): string {
  const { gy, gm, gd } = toGregorian(jy, jm, jd);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${gy}-${pad(gm)}-${pad(gd)}`;
}

export function currentJalaliYear(): number {
  return toJalaali(new Date()).jy;
}

export function daysInJalaliMonth(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  // Esfand is 30 days in a leap year, 29 otherwise. Rather than reimplement
  // the leap rule, ask the calendar: if day 30 round-trips, the year is leap.
  const { gy, gm, gd } = toGregorian(jy, 12, 30);
  return toJalaali(new Date(gy, gm - 1, gd)).jm === 12 ? 30 : 29;
}

const JALALI_WEEKDAYS = [
  "شنبه",
  "یکشنبه",
  "دوشنبه",
  "سه‌شنبه",
  "چهارشنبه",
  "پنجشنبه",
  "جمعه",
];

/** HH:MM in Persian digits — what goes under a message bubble. */
export function clockTime(iso: string): string {
  const date = new Date(iso);
  return faNum(
    `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`,
  );
}

/** A stable key for "which day is this message on", in local time. */
export function dayKey(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/**
 * The label on a date divider.
 *
 * "امروز" and "دیروز" first, because that is what people actually need to
 * know; anything older gets the Jalali date, since a Gregorian one in a
 * Persian chat is a small daily friction.
 */
export function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (dayKey(iso) === dayKey(today.toISOString())) return "امروز";
  if (dayKey(iso) === dayKey(yesterday.toISOString())) return "دیروز";

  const { jy, jm, jd } = toJalaali(date);
  const weekday = JALALI_WEEKDAYS[(date.getDay() + 1) % 7] ?? "";
  return `${weekday} ${faNum(jd)} ${JALALI_MONTHS[jm - 1]} ${faNum(jy)}`;
}
