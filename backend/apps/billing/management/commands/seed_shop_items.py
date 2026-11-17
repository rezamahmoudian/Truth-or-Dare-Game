from django.core.management.base import BaseCommand
from django.db import transaction
from apps.billing.models import Product, DigitalItem
from apps.game.models import Prompt


GOODS = [
    ("frame-aurora", "قاب شفق", "FRAME", "aurora", "حلقه‌ای از بنفش و سبز روشن دور عکس تو."),
    ("frame-rose", "قاب رز", "FRAME", "rose", "یک قاب صورتی گرم برای پروفایلت."),
    ("frame-ocean", "قاب اقیانوس", "FRAME", "ocean", "آبی آرام، با یک درخشش کوچک."),
    ("name-lilac", "نام یاسی", "NAME", "lilac", "نامت با رنگ یاسی در چت و پروفایل نمایش داده می‌شود."),
    ("name-mint", "نام نعنایی", "NAME", "mint", "یک رنگ تازه برای نام تو."),
    ("name-peach", "نام هلویی", "NAME", "peach", "رنگ گرم و روشن برای نامت."),
    ("badge-star", "نشان ستاره", "BADGE", "star", "یک ستاره کنار نامت؛ نشان تزئینی، مستقل از افتخارات بازی."),
    ("badge-moon", "نشان ماه", "BADGE", "moon", "برای شب‌نشینی‌های طولانی."),
    ("theme-forest", "تم جنگل شب", "THEME", "forest", "ظاهر چت برای خودت به سبز شب تغییر می‌کند."),
    ("theme-sunset", "تم غروب", "THEME", "sunset", "حال‌وهوای گرم در صفحهٔ چت خودت."),
    ("effect-sparkle", "درخشش پیام", "EFFECT", "sparkle", "درخشش کوتاه روی پیام‌ها؛ با رعایت تنظیم کاهش حرکت."),
    ("effect-hearts", "قلب پیام", "EFFECT", "hearts", "یک قلب کوچک کنار پیام‌هایت."),
    ("sticker-party", "استیکر جشن", "STICKER", "party", "استیکر بزرگ جشن؛ استفادهٔ نامحدود در چت."),
    ("sticker-highfive", "استیکر بزن قدش", "STICKER", "highfive", "یک بزن‌قدش برای هم‌بازی پایه‌ات."),
    ("reaction-diamond", "واکنش الماس", "REACTION", "💎", "واکنش الماس به پیام‌های دوست‌داشتنی."),
    ("reaction-magic", "واکنش جادویی", "REACTION", "🪄", "واکنش جادویی برای چت."),
    ("gift-rose", "یک شاخه رز", "GIFT", "rose", "یک هدیه برای ارسال در چت؛ هر خرید یک ارسال."),
    ("gift-coffee", "یک فنجان رفاقت", "GIFT", "coffee", "دعوت نمادین به یک قهوه؛ بدون ارزش نقدی."),
    ("gift-star", "ستارهٔ رفاقت", "GIFT", "star", "یک ستاره برای کسی که گفت‌وگو را قشنگ‌تر کرده."),
    ("spotlight-15", "Spotlight پانزده‌دقیقه‌ای", "SPOTLIGHT", "spotlight", "یک بار نمایش ویژه بین کاربران آنلاین؛ آنلاین بمان. مچ تضمین نمی‌شود."),
]

PACKS = [
    ("deep", "حرف‌های عمیق", "DEEP", [
        "کدام تصمیم کوچک تو، مسیر یک سال کامل از زندگیت را عوض کرد؟ اگر دوباره برگردی همان را انتخاب می‌کنی؟",
        "وقتی هیچ‌کس قرار نیست نتیجه را ببیند، هنوز کدام کار را با تمام دقت انجام می‌دهی؟ چرا؟",
        "چه موفقیتی را اگر امروز دوباره به دست بیاوری، دیگر مثل گذشته خوشحالت نمی‌کند؟ چه چیزی عوض شده؟",
        "اگر قرار باشد یک باور قدیمی خودت را برای یک روز کنار بگذاری، کدام را انتخاب می‌کنی و چه چیزی را امتحان می‌کنی؟",
    ]),
    ("private", "بین خودمان", "FUNNY", [
        "آخرین بار کجا وانمود کردی بی‌تفاوتی، درحالی‌که دلت می‌خواست کسی یک سؤال دیگر ازت بپرسد؟",
        "کدام جملهٔ ساده را از یک آدم مشخص منتظری؟ اگر هیچ‌وقت نگوید، خودت چه کاری می‌توانی بکنی؟",
        "چه چیزی را در شروع آشنایی از خودت کمتر نشان می‌دهی چون می‌ترسی اشتباه برداشت شود؟",
        "اگر یکی از سکوت‌های تو زیرنویس داشت، دوست داشتی طرف مقابل چه جمله‌ای را بخواند؟",
    ]),
    ("bold", "یک قدم جسورتر", "BOLD", [
        "اگر از جواب من مطمئن بودی، برای اولین قرار چه پیشنهاد متفاوتی می‌دادی؟",
        "کدام تعریف صادقانه را بلد نیستی بدون خجالت بگویی؟ همین‌جا یک نسخهٔ تمرینی‌اش را بگو.",
        "چه چیزی در یک گفت‌وگوی عادی باعث می‌شود ناگهان احساس کنی بین شما کششی هست؟",
        "برای نزدیک‌ترشدن، بیشتر از گفتن خواسته‌ات می‌ترسی یا شنیدن خواستهٔ طرف مقابل؟ چرا؟",
    ]),
    ("couples", "قرار دونفره", "FUNNY", [
        "یک رسم کوچک دونفره بساز که حتی در هفته‌های شلوغ بتوانید حفظش کنید؛ چه رسم و چرا؟",
        "وقتی اختلاف دارید، چه جمله‌ای کمک می‌کند دوباره حس کنید هم‌تیمی هستید؟",
        "کدام شکل توجه را کمتر درخواست می‌کنی، درحالی‌که دریافتش روزت را بهتر می‌کند؟",
        "اگر یک قرار با بودجهٔ نزدیک به صفر بچینید، چه برنامه‌ای بیشترین خاطره را می‌سازد؟",
    ]),
    ("fun", "خنده‌دارتر از همیشه", "FRIENDLY", [
        "اگر تلفنت از تو استعفا بدهد، سه دلیل اصلی‌اش چه خواهد بود؟ از زبان خودش تعریف کن.",
        "برای بدترین عادتت یک نام شیک شرکتی انتخاب کن و توضیح بده چرا باید بابتش حقوق بگیری.",
        "اگر یک نفر تمام بهانه‌های تو را جمع کند و کتاب بسازد، اسم کتاب و فصل اولش چیست؟",
        "یک روز معمولی خودت را مثل تریلر فیلم اکشن تعریف کن؛ کدام کار ساده نقش نبرد نهایی را دارد؟",
    ]),
    ("yalda", "شب‌نشینی یلدا", "FRIENDLY", [
        "اگر برای هر دوستت یک میوهٔ یلدایی انتخاب کنی، برای هم‌بازی این چت چه انتخابی داری و چرا؟",
        "کدام خاطرهٔ خانوادگی هر سال با جزئیات اغراق‌آمیزتری تعریف می‌شود؟ نسخهٔ واقعی‌اش چیست؟",
        "یک فال خیالی برای سال آیندهٔ هم‌بازی‌ات بساز که هم خنده‌دار باشد هم امیدوارکننده.",
        "اگر قرار باشد طولانی‌ترین شب سال را فقط با یک موضوع گفت‌وگو بگذرانید، چه موضوعی تمام نمی‌شود؟",
    ]),
]

PACK_DARES = [
    "یک نامهٔ سه‌جمله‌ای از زبان خودت در پنج سال آینده بنویس؛ یک تشکر، یک هشدار و یک آرزو داشته باشد.",
    "یک سوءتفاهم کوچک دربارهٔ شخصیتت را بدون اسم‌بردن از کسی توضیح بده و بگو دوست داشتی چطور شناخته شوی.",
    "یک دعوت محترمانه و جسورانه برای قرار خیالی بنویس که هم علاقه‌ات را نشان بدهد هم ردکردنش راحت باشد.",
    "یک برنامهٔ دونفرهٔ بیست‌دقیقه‌ای برای بهترکردن یک روز خسته‌کننده پیشنهاد بده و از هم‌بازی‌ات بخواه یک بخشش را عوض کند.",
    "از زبان یک کفش گمشده، سه پیام پشت‌سرهم به صاحبش بنویس؛ هر پیام از قبلی طلبکارتر باشد.",
    "برای هم‌بازی‌ات یک فال یلدایی دوخطی بساز که کلمات انار، آسانسور و رفاقت حتماً در آن باشند.",
]


class Command(BaseCommand):
    help = "Create inactive digital goods and new prompt packs awaiting admin review; never set prices."

    @transaction.atomic
    def handle(self, **options):
        for index, (key, title, kind, visual, description) in enumerate(GOODS):
            product, _ = Product.objects.get_or_create(key=key, defaults=dict(title=title, description=description, kind="ITEM", credits=0, sort_order=200 + index))
            DigitalItem.objects.get_or_create(product=product, defaults=dict(kind=kind, visual=visual))
        count = 0
        for index, (key, title, category, questions) in enumerate(PACKS):
            product, _ = Product.objects.get_or_create(key=f"pack-{key}", defaults=dict(title=title, description="سؤال‌های تازه برای بزرگسالان؛ انتخاب از دکمهٔ بازی در چت. محتوای پایه همچنان رایگان است.", kind="ITEM", credits=0, sort_order=250 + index))
            item, _ = DigitalItem.objects.get_or_create(product=product, defaults=dict(kind="PACK", visual="cards"))
            for text in questions:
                _, created = Prompt.objects.get_or_create(text=text, defaults=dict(pack=item, type="TRUTH", category=category,
                    intensity=2, is_active=False, review_status="PENDING"))
                count += created
            _, created = Prompt.objects.get_or_create(text=PACK_DARES[index], defaults=dict(pack=item, type="DARE", category=category,
                intensity=2, is_active=False, review_status="PENDING"))
            count += created
        self.stdout.write(self.style.SUCCESS(f"26 draft items ready; {count} new prompts await review. No prices, orders or grants created."))
