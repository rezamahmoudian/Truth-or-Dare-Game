# استقرار و انتشار

این راهنما از یک سرور خالی تا APK آماده برای بازار و مایکت است.

---

## ۱. سرور

- یک VPS لینوکسی با Docker و Docker Compose (نسخه ۲.۲۴ به بالا — فایل پروداکشن از
  `!reset` و `!override` استفاده می‌کند)
- حداقل ۲ هسته و ۲ گیگ رم برای شروع
- **ارائه‌دهنده‌ای که از ایران قابل دسترس باشد** — لیارا، آروان‌کلود، یا VPS
  داخلی/خارجی بدون مسدودی. Vercel، Netlify و Cloudflare Pages برای توسعه‌دهنده و
  کاربر ایرانی بسته‌اند.
- پورت‌های ۸۰ و ۴۴۳ باز

## ۲. دامنه

یک رکورد `A` برای دامنه به IP سرور بسازید. **قبل از اولین اجرا** باید برقرار باشد —
Caddy هنگام شروع گواهی TLS می‌گیرد و اگر DNS هنوز جا نیفتاده باشد، شکست می‌خورد.

## ۳. تنظیمات

```bash
cp .env.production.example .env.production
```

حتماً عوض کنید:

| متغیر | |
|---|---|
| `DOMAIN` | دامنه‌ی شما |
| `DJANGO_SECRET_KEY` | یک رشته‌ی تصادفی بلند |
| `POSTGRES_PASSWORD` | رمز قوی |
| `ALLOWED_HOSTS` | دامنه + `backend` |
| `CSRF_TRUSTED_ORIGINS` | `https://` + دامنه |

ساخت کلید:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

## ۴. اجرا

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**`--env-file` را جا نیندازید.** رمز Postgres از همین فایل خوانده می‌شود؛ بدونش
دیتابیس با رمز پیش‌فرض توسعه بالا می‌آید.

داده‌های اولیه (فقط بار اول):

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec backend python manage.py seed_prompts
```

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec backend python manage.py seed_match_modes
```

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec backend python manage.py seed_banned_words
```

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

## ۵. بررسی

```bash
bash scripts/verify_prod.sh https://دامنه
```

۳۳ بررسی: پوسته، مسیرهای عمیق، manifest، آیکون‌ها، هدرهای کش، فونت، API، فایل‌های
استاتیک، `assetlinks.json`، هدرهای امنیتی، بسته بودن پورت دیتابیس، و نبودن صفحه‌ی
debug.

**یک چیز را فقط مرورگر واقعی می‌تواند بسنجد:** در Chrome سایت را باز کنید،
`DevTools → Application → Service Workers` باید `sw.js` را «activated and running»
نشان دهد، و در Chrome اندروید منوی «Install app» ظاهر شود.

در پروداکشن فقط Caddy روی میزبان پورت دارد. Postgres و Redis از بیرون قابل دسترس
نیستند — دیتابیسی که از اینترنت دیده شود، رایج‌ترین راهی است که یک محصول کوچک
داده‌ی کاربرانش را از دست می‌دهد.

---

## ۶. ساخت APK (TWA)

APK یک پوسته‌ی Chrome دور همان وب‌اپ است. **کد یکی است**؛ هر به‌روزرسانی سایت
بلافاصله در اپ هم هست، بدون انتشار دوباره.

### نصب ابزار

روی سیستم خودتان (نه سرور)، با Node 18+ و JDK 17:

```bash
npm i -g @bubblewrap/cli
```

### تنظیم

در `twa/twa-manifest.json` همه‌ی `jorat.example.ir` ها را با دامنه‌ی واقعی عوض
کنید.

> **`packageId` را قبل از اولین انتشار قطعی کنید.** بعد از انتشار در هیچ فروشگاهی
> قابل تغییر نیست — عوض کردنش یعنی یک اپ جدید با صفر نصب.
> پیشنهاد فعلی: `ir.jorat.app`

### ساخت

```bash
cd twa
```

```bash
bubblewrap init --manifest https://دامنه/manifest.webmanifest
```

```bash
bubblewrap build
```

خروجی: `app-release-signed.apk` و `app-release-bundle.aab`

بار اول Bubblewrap یک کلید امضا (`android.keystore`) می‌سازد.

> **از `android.keystore` و رمزش نسخه‌ی پشتیبان جای امن بگیرید.** اگر گم شود،
> هیچ‌وقت نمی‌توانید به‌روزرسانی همان اپ را منتشر کنید. در `.gitignore` است و
> نباید وارد مخزن شود.

### اتصال APK به دامنه

بدون این مرحله اپ نوار آدرس مرورگر را نشان می‌دهد و شبیه یک سایت باز شده است.

۱. اثر انگشت کلید:

```bash
keytool -list -v -keystore android.keystore -alias jorat
```

۲. مقدار `SHA256` را در `caddy/site/.well-known/assetlinks.json` جای
`REPLACE_WITH_...` بگذارید (و `package_name` را اگر عوض کرده‌اید).

۳. Caddy را ری‌استارت کنید و بررسی کنید:

`https://دامنه/.well-known/assetlinks.json`

---

## ۷. انتشار در فروشگاه‌ها

**کافه‌بازار** و **مایکت** هر دو APK معمولی می‌پذیرند. برای هر دو آماده باشید:

- اسکرین‌شات‌ها (حداقل ۴، از صفحه‌ی اصلی، چت، بازی، دوستان)
- توضیحات فارسی
- **رده‌ی سنی ۱۸+** — اپ غریبه‌ها را در چت خصوصی کنار هم می‌گذارد و محتوای «جرئت»
  دارد
- **سیاست حریم خصوصی** به‌صورت یک صفحه‌ی عمومی
- پاسخ به سؤالات بررسی درباره‌ی گزارش تخلف، بلاک و فیلتر محتوا — همه پیاده‌سازی
  شده‌اند (README بخش «ایمنی»)

لینک مستقیم دانلود APK هم می‌تواند روی خود سایت باشد.

---

## ۸. به‌روزرسانی

```bash
git pull
```

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

کاربران وب و APK هر دو نسخه‌ی جدید را می‌گیرند؛ اپ یک پیام «نسخه‌ی جدید آماده است»
نشان می‌دهد و **خودش وسط گفتگو ری‌لود نمی‌کند**.

APK فقط وقتی دوباره ساخته می‌شود که آیکون، نام یا `packageId` عوض شود — و آن‌وقت
`appVersionCode` را یکی بالا ببرید.

## ۹. پشتیبان

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec -T db pg_dump -U ft ft > backup-$(date +%F).sql
```

این را روزانه و خارج از همان سرور نگه دارید.
