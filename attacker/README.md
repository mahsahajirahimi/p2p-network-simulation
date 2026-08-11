# ماژول مهاجم

این پوشه تمام بخش‌های مربوط به نفر دوم پروژه را در بر دارد: انتخاب و مشاهده جاسوس‌ها، حمله پایه و پیشرفته، تأخیر عمدی فاز ۵، ارزیابی، تحلیل آزمایش‌ها، نمودارها، تست‌ها و قرارداد ارتباط با شبکه.

الگوریتم‌های حمله هیچ‌گاه مبدأ واقعی یا زمان ایجاد بسته را دریافت نمی‌کنند. این اطلاعات فقط پس از پایان پیش‌بینی در اختیار ارزیاب قرار می‌گیرد.

## ساختار پوشه

```text
attacker/
├── advanced_attack.py       # حمله زمان‌بندی پیشرفته با شبیه‌سازی Monte Carlo
├── attacker_service.py      # اجرای یک حمله روی همه بسته‌ها
├── baseline_attack.py       # حمله پایه اولین جاسوس مشاهده‌کننده
├── deliberate_delay.py      # سیاست‌های تأخیر مجاز فاز ۵
├── evaluator.py             # محاسبه دقت، Score_adv، T80 و Score_honest
├── io.py                    # خواندن و نوشتن JSON و JSONL
├── models.py                # مدل‌های داده مشترک
├── spy_observer.py          # ثبت مشاهده محلی جاسوس
├── spy_selector.py          # انتخاب جاسوس با سقف ۳۰٪ گره‌ها
├── analysis/                # اجرا، تجمیع، اعتبارسنجی و رسم نمودارها
├── config/                  # تنظیمات مهاجم
├── tests/                   # تست‌های واحد
├── pytest.ini
└── requirements.txt
```

## قرارداد ارتباط شبکه و مهاجم

بسته UDP فقط شامل شناسه بسته و وضعیت آن است:

```json
{"pid":"abc123","status":"STEM"}
```

فیلدهای `true_source` و `created_at` نباید در بسته شبکه یا ورودی الگوریتم حمله ظاهر شوند.

هر جاسوس پیش از اعمال تأخیر احتمالی، مشاهده محلی زیر را ثبت می‌کند:

```json
{"packet_id":"abc123","spy_id":"Node_7","from_node":"Node_5","received_at":12.481,"state":"STEM"}
```

جاسوس اجازه حذف یا توقف بسته را ندارد. تأخیر اضافه آن روی هر لینک نیز همیشه بین صفر و تأخیر پایه همان لینک است.

حقیقت مرجع فقط برای ارزیابی و در فایل جداگانه `reference_truth.jsonl` ذخیره می‌شود:

```json
{"packet_id":"abc123","true_source":"Node_3","created_at":12.400,"t80":0.812}
```

مقدار `t80` زمان سپری‌شده تا رسیدن بسته به `ceil(0.8 * N)` گره متمایز، با احتساب گره مبدأ، است. الگوریتم ابتدا همه پیش‌بینی‌ها را کامل می‌کند و فقط پس از آن ارزیاب حقیقت مرجع را می‌خواند.

ساختار خروجی هر اجرا به شکل زیر است:

```text
datasets/<run-name>/
├── manifest.json
├── node_ids.json
├── topology.json
├── source_plan.json
├── simulation.log
├── ground_truth.log
├── spy_observations.jsonl
└── reference_truth.jsonl
```

قوانین جداسازی اطلاعات:

- گره عادی فقط `pid` و `status` را می‌بیند.
- جاسوس علاوه بر آن، فرستنده مستقیم و زمان دریافت محلی را می‌داند.
- الگوریتم حمله می‌تواند تأخیر پایه لینک‌ها و مشاهدات جاسوس را بخواند.
- فقط ارزیاب اجازه خواندن `reference_truth.jsonl` را دارد.

## نصب وابستگی‌ها

همه دستورها را از ریشه مخزن اجرا کنید:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r attacker/requirements.txt
```

## اجرای تست‌ها

تست‌های مهاجم:

```bash
python -m pytest -c attacker/pytest.ini attacker/tests
```

تست‌های شبکه:

```bash
python -m pytest -c network/pytest.ini network/tests
```

برای اجرای یک فایل تست مشخص:

```bash
python -m pytest \
  -c attacker/pytest.ini attacker/tests/test_evaluator.py -v
```

## اجرای یک سناریوی تکی

فاز ۲، انتشار عمومی همراه با جاسوس:

```bash
python -m network.simulator \
  --phase 2 --seed 101 --packets 200 --spy-count 3 \
  --output-dir datasets/phase2_seed101_spies3
```

فاز ۴، Dandelion همراه با حمله پیشرفته:

```bash
python -m network.simulator \
  --phase 4 --seed 101 --packets 200 --p 0.9 --spy-count 3 \
  --output-dir datasets/phase4_p0.9_seed101_spies3
```

فاز ۵، اعمال بیشترین تأخیر مجاز:

```bash
python -m network.simulator \
  --phase 5 --seed 101 --packets 200 --p 0.9 --spy-count 3 \
  --delay-mode maximum \
  --output-dir datasets/phase5_p0.9_seed101_spies3_delay_maximum
```

هر اجرا فایل‌های `manifest.json`، `topology.json`، `node_ids.json`، `source_plan.json`، `spy_observations.jsonl` و `reference_truth.jsonl` را تولید می‌کند.

## اجرای کامل پنج فاز

برای مقایسه منصفانه، همه فازها باید از ۲۰۰ بسته، پنج seed یکسان، توپولوژی‌های یکسان و source plan مشترک استفاده کنند.

ابتدا فازهای ۱ و ۲ را اجرا کنید:

```bash
python -m network.experiment_runner \
  --stage phase1 --dataset-root datasets --duration 10 --grace 12

python -m network.experiment_runner \
  --stage phase2 --dataset-root datasets --duration 10 --grace 8
```

نتایج فاز ۲ را تحلیل کنید تا تعداد جاسوس با بیشترین میانگین `Score_adv` به دست آید:

```bash
python -m attacker.analysis.run_experiments \
  --dataset-root datasets --output results/phase2 --phase 2

python -m attacker.analysis.aggregate_results \
  --input results/phase2/raw_results.csv \
  --output results/phase2/summary.csv

python -m attacker.analysis.recommend_configuration \
  --input results/phase2/summary.csv
```

در اجرای فعلی، تعداد بهینه جاسوس برابر ۳ است. سپس فازهای ۳ تا ۵ را اجرا کنید:

```bash
python -m network.experiment_runner \
  --stage phase3 --dataset-root datasets --duration 10 --grace 12

python -m network.experiment_runner \
  --stage phase4 --dataset-root datasets --duration 10 --grace 12 \
  --spy-count 3

python -m network.experiment_runner \
  --stage phase5 --dataset-root datasets --duration 10 --grace 12 \
  --spy-count 3
```

برای مشاهده دستورهای ماتریس بدون اجرای پردازه‌ها، گزینه `--dry-run` را اضافه کنید.

## اعتبارسنجی آزمایش‌ها

```bash
python -m attacker.analysis.validate_experiments \
  --dataset-root datasets
```

اعتبارسنج موارد زیر را کنترل می‌کند:

- وجود هر پنج فاز و همه فایل‌های ضروری؛
- وجود ۲۰۰ بسته و حداقل پنج seed؛
- درستی هندسه، تأخیرها و همبندی توپولوژی؛
- محدودیت ۳۰٪ جاسوس و درستکاربودن تمام مبدأها؛
- یکسان‌بودن topology، source plan و مجموعه‌های تودرتوی جاسوس‌ها؛
- کامل‌بودن sweep تعداد جاسوس در فاز ۲؛
- وجود هر سه مقدار `p` و همه سیاست‌های تأخیر فاز ۵؛
- نبود اطلاعات حقیقت مرجع در لاگ جاسوس‌ها.

خروجی معتبر فعلی باید پیام زیر را نشان دهد:

```text
Validated 125 run directories successfully
```

## تحلیل نهایی و نمودارها

```bash
python -m attacker.analysis.run_experiments \
  --dataset-root datasets --output results/attacker --workers 4

python -m attacker.analysis.aggregate_results \
  --input results/attacker/raw_results.csv \
  --output results/attacker/summary.csv

python -m attacker.analysis.plot_results \
  --input results/attacker/summary.csv \
  --output-dir results/attacker/plots
```

نمودارهای تولیدشده عبارت‌اند از:

- دقت و `Score_adv` نسبت به تعداد جاسوس در فاز ۲؛
- مقدار `T80` نسبت به `p` در فاز ۳؛
- مقایسه دقت حمله پایه و پیشرفته در فاز ۴؛
- دقت، `T80` و `Score_honest` نسبت به سیاست تأخیر در فاز ۵.

هر نقطه نمودار دارای میله خطای انحراف معیار نمونه است. فایل `summary.csv` نیز میانگین، میانه و انحراف معیار خواسته‌شده در صورت پروژه را نگه می‌دارد.

## نتایج فعلی

- تعداد سناریوهای معتبر: ۱۲۵
- تعداد بسته در هر سناریو: ۲۰۰
- تعداد seed: پنج
- تعداد بهینه جاسوس: ۳
- روش برتر: `advanced_timing`
- میانگین دقت روش برتر در فاز ۲: `0.672`
- میانگین `Score_adv` روش برتر: `0.224`
- تعداد تست‌های موفق: ۲۰

## ساخت فایل تحویل نهایی

این مرحله فقط پس از آماده‌شدن گزارش و ویدیو انجام می‌شود و در وضعیت فعلی پروژه عمداً اجرا نشده است:

```bash
python -m attacker.analysis.package_submission \
  --student-id-1 YOUR_ID --student-id-2 TEAMMATE_ID \
  --report path/to/Report.pdf --video path/to/Video.mp4
```

این دستور metadata گیت، محیط مجازی، cache، داده‌های خام و نتایج تولیدشده را از پوشه `Code/` کنار می‌گذارد و در صورت نبود PDF یا MP4 متوقف می‌شود.

## تضمین مقایسه منصفانه

برای هر seed، اجراکننده آزمایش موارد زیر را میان فازها ثابت نگه می‌دارد:

- توپولوژی تولیدشده و شناسه پایدار گره‌ها؛
- شناسه بسته‌ها، زمان‌های تزریق و مبدأهای درستکار؛
- مجموعه‌های تودرتوی جاسوس‌ها برای تعدادهای مختلف؛
- seedهای یکسان برای `p = 0.9, 0.5, 0.1`.

مبدأ بسته‌ها از میان گره‌هایی انتخاب می‌شود که حتی در بزرگ‌ترین مجموعه جاسوس‌ها نیز حضور ندارند.

## چک‌لیست انطباق با صورت پروژه

موارد زیر پیاده‌سازی و بررسی شده‌اند:

- [x] اجرای هر گره در یک پردازه مستقل با پورت UDP مجزا روی `localhost`؛
- [x] مدیریت هم‌روندی و ارسال‌های تأخیردار با `asyncio`؛
- [x] تولید ۲۰ تا ۳۰ گره در صفحه ۱۰۰۰ در ۱۰۰۰ با چهار تا شش کلاستر؛
- [x] همبندی شبکه و وجود دست‌کم دو لینک خارجی مستقل برای هر کلاستر؛
- [x] تأخیر پایه یک میلی‌ثانیه بر واحد فاصله و جیتر مثبت و منفی ۲۰٪؛
- [x] جلوگیری از افشای مبدأ و زمان ایجاد در بسته شبکه؛
- [x] محدودیت تعداد جاسوس‌ها به حداکثر ۳۰٪ گره‌ها؛
- [x] انتخاب تمام مبدأها از میان گره‌های درستکار؛
- [x] حمله پایه اولین جاسوس و حمله زمان‌بندی پیشرفته Monte Carlo؛
- [x] Dandelion با `p = 0.9`، `0.5` و `0.1` و embargo ایمن مبدأ؛
- [x] سیاست‌های تأخیر `none`، `half`، `maximum` و `random` بدون حذف بسته؛
- [x] محاسبه `T80`، `Score_adv` و `Score_honest` طبق فرمول صورت پروژه؛
- [x] پنج seed، ۲۰۰ بسته در هر اجرا و source plan مشترک برای مقایسه منصفانه؛
- [x] اجرای موفق و اعتبارسنجی هر ۱۲۵ سناریو؛
- [x] تولید میانگین، میانه، انحراف معیار و هفت نمودار نهایی؛
- [x] اجرای موفق ۲۰ تست شبکه و مهاجم.

موارد باقی‌مانده برای تحویل انسانی:

- [ ] نوشتن `Report.pdf`؛
- [ ] ضبط `Video.mp4` حداکثر ۱۵ دقیقه‌ای؛
- [ ] ساخت و بازبینی ZIP نهایی شامل `Code/`، گزارش و ویدیو.
