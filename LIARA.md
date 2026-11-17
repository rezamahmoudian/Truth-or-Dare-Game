# استقرار روی لیارا

خطای `the Dockerfile (Dockerfile) cannot be empty` به دلیل نبود Dockerfile در ریشهٔ مخزن بود. Dockerfile ریشه اکنون فرانت‌اند را می‌سازد و Django، Nginx، Celery worker و Celery beat را اجرا می‌کند. Docker Compose قبلی برای توسعه و VPS همچنان جداست.

## پیش‌نیازهای پنل

1. برنامهٔ `truthordare` با پلتفرم **Docker**، پوشهٔ ساخت ریشهٔ مخزن، Dockerfile برابر `Dockerfile` و پورت **3000**.
2. PostgreSQL و Redis قابل دسترس از برنامه؛ آدرس‌های اتصال را از پنل همان سرویس‌ها بگیرید. از `localhost` استفاده نکنید. داده‌های PostgreSQL باید دائمی باشند؛ Redis را برای صف‌ها با persistence و بدون eviction تنظیم کنید.
3. یک دیسک دائمی به نام **uploads** بسازید و به **`/app/private_media`** متصل کنید. این اتصال در `liara.json` هم تعریف شده؛ اگر از پنل GitHub Deploy استفاده می‌کنید، اتصال دیسک را در پنل نیز بررسی کنید. فایل‌های کاربران نباید روی فایل‌سیستم موقت کانتینر بمانند.
4. تعداد نمونه‌های برنامه **۱** باشد. در این چینش Beat داخل برنامه است؛ استقرار هم‌پوشان/Zero-downtime را غیرفعال کنید تا دو زمان‌بند هم‌زمان اجرا نشوند. این روش هنگام انتشار وقفهٔ کوتاه دارد. برای چند replica یا انتشار بدون وقفه، ابتدا Beat را به سرویس اختصاصی تک‌نمونه منتقل کنید.

## متغیرهای محیطی

فهرست آماده در [`deploy/liara/env.example`](deploy/liara/env.example) است. مقادیر واقعی را در بخش متغیرهای محیطی برنامه وارد کنید؛ فایل `.env` سیستم توسعه داخل ایمیج کپی نمی‌شود.

- `DJANGO_SECRET_KEY`: کلید جدید و تصادفی، حداقل ۳۲ کاراکتر. تولید با `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- `DATABASE_URL` و `REDIS_URL`: رشتهٔ اتصال سرویس‌های واقعی؛ کاراکترهای خاص رمز در URL باید percent-encode شوند.
- `ALLOWED_HOSTS`: دامنه بدون پروتکل؛ چند دامنه با کاما.
- `CSRF_TRUSTED_ORIGINS` و `CORS_ALLOWED_ORIGINS`: دامنه با `https://`؛ نمونه‌ها برای `truthordare.liara.run` هستند، با دامنهٔ واقعی برنامه تطبیق دهید.
- `DEBUG=False` و `BILLING_PUBLIC_BASE_URL` برابر آدرس عمومی HTTPS.
- `NUM_PROXIES=2` برای پروکسی لیارا و Nginx داخلی در نظر گرفته شده؛ در صورت اضافه‌کردن CDN، زنجیرهٔ پروکسی و IP واقعی را بررسی کنید.
- برای منابع کم می‌توانید `UVICORN_WORKERS=1` و `CELERY_CONCURRENCY=1` بگذارید. ظرفیت واقعی را زیر بار اندازه‌گیری کنید.

برای هوش مصنوعی، مقدارهای `AI_PROVIDER`، مدل، آدرس و کلید همان سرویس موردنظر را در پنل وارد کنید. نمونهٔ فایل برای Anthropic gateway فعلی است. برای برگشت به سرویس قبلی، `AI_PROVIDER=openai` و **مقادیر قبلی خودتان** برای `OPENAI_BASE_URL`، `OPENAI_MODEL`، `OPENAI_API_KEY` و در صورت نیاز `OPENAI_EXTRA_HEADERS` را وارد کنید؛ نمونهٔ OpenAI در فایل، API استاندارد است و معادل تنظیمات قبلی Codex نیست. تا وقتی کلید و تنظیمات مدل کامل نشده، مچ با AI را در ادمین فعال نکنید.

## انتشار و داده‌های اولیه

بعد از قرارگرفتن تغییرات روی شاخهٔ `main`، همان شاخه را از بخش استقرار GitHub منتشر کنید. شروع برنامه ابتدا تنظیمات و اتصال سرویس‌ها را بررسی می‌کند، سپس `migrate` و `collectstatic` اجرا می‌شوند. هیچ حساب ادمین یا رمز پیش‌فرضی ساخته نمی‌شود.

پس از اولین استقرار موفق، در ترمینال برنامه اجرا کنید:

```sh
python manage.py createsuperuser
python manage.py seed_prompts
python manage.py seed_match_modes
python manage.py seed_banned_words
python manage.py seed_billing_products
python manage.py seed_shop_items
```

در صورت نیاز به شخصیت‌های نمونه:

```sh
python manage.py seed_ai_personas
gosu app python manage.py seed_ai_portraits
```

این فرمان‌ها دیتابیس تازه را مقداردهی می‌کنند؛ برای انتقال کاربران، چت‌ها، تنظیمات و بازبینی سوال‌های فعلی باید backup دیتابیس و فایل‌های خصوصی را جداگانه منتقل کنید. قبل از migration روی دیتابیس موجود backup بگیرید.

## بررسی استقرار

- `/` و لینک مستقیم `/chat` باید فرانت‌اند را نمایش دهند.
- `/admin/login/` باید همراه CSS باز شود و ورود روی HTTPS خطای CSRF ندهد.
- `/api/health/` باید HTTP 200 بدهد.
- داخل ترمینال: `python /app/deploy/liara/healthcheck.py` باید با کد صفر تمام شود.
- `supervisorctl -c /app/deploy/liara/supervisord.conf status` باید چهار پردازش `web`، `worker`، `beat` و `nginx` را RUNNING نشان دهد.
- با دو حساب آزمایشی، مچ‌شدن و ارسال پیام را روی دامنهٔ HTTPS امتحان کنید. برای وویس، دسترسی میکروفن مرورگر لازم است.
- فایل پروفایل/ضمیمه را آپلود کنید و بعد از استقرار مجدد باقی‌ماندن آن را بررسی کنید. `/private_media/` و `/media/` عمداً عمومی نیستند؛ دریافت فایل از API دارای کنترل دسترسی انجام می‌شود.

لاگ‌های worker و beat در لاگ برنامه دیده می‌شوند. اگر صفحه باز می‌شود ولی مچ یا AI کار نمی‌کند، وضعیت این دو پردازش و اتصال Redis را بررسی کنید. برای مشکلات شروع برنامه، پیام‌های preflight نام متغیر ناقص را نشان می‌دهند و مقدار رمز را چاپ نمی‌کنند.

## تست تکرارپذیر قبل از انتشار

این محیط دیتابیس و فایل آزمایشی جدا دارد و هیچ پورتی را عمومی نمی‌کند:

```sh
python -m unittest discover -s deploy/liara -p test_preflight.py -v
docker compose -f deploy/liara/compose.smoke.yml up -d --build --wait --wait-timeout 180
docker compose -f deploy/liara/compose.smoke.yml exec -T app python deploy/liara/smoke.py
docker compose -f deploy/liara/compose.smoke.yml down -v
```

تست اجرا، فرانت‌اند و مسیرهای مستقیم، API، CSS ادمین، CSRF پشت پروکسی HTTPS، WebSocket احراز‌شده، اجرای واقعی task مچ‌شدن و قابلیت نوشتن فایل توسط کاربر محدود برنامه را بررسی می‌کند. اسکریپت روی دیتابیس غیرآزمایشی اجرا نمی‌شود. فرمان آخر فقط منابع همین محیط آزمایشی را پاک می‌کند.
