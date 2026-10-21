# برنامج التدريب - نسخة التطبيق (as3_app.py)
# نفس as3.py، لكن يمكن التحكم فيه من تطبيق الويب (app/index.html) عبر البلوتوث
# بدلاً من أزرار الروبوت فقط. أزرار الروبوت ما زالت تعمل كالمعتاد.
# أوامر التطبيق (حرف واحد): R=تسجيل حركة، L=قراءة حساسات، C=طباعة البرنامج،
# F=نقطة خط ذكية، T=متابعة خط، U=تراجع.
# التحكم عن بعد (أزرار الأسهم): w=للأمام s=للخلف a=لف يسارًا d=لف يمينًا x=إيقاف.
# إرسال الكود من التطبيق: K=بدء الاستلام ثم أسطر الكود ثم E=انتهى،
#   و G=نفّذ الكود المستلم الآن، و x=إيقاف التنفيذ.

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, ColorSensor
from pybricks.parameters import Port, Button, Direction, Color
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch

# مدخل قياسي لاستقبال أوامر تطبيق الويب عبر البلوتوث (Pybricks stdin)
from usys import stdin
from uselect import poll

# =========================================================
# 1) المنافذ حسب روبوتك
# =========================================================
hub = PrimeHub()

left_motor  = Motor(Port.A, Direction.COUNTERCLOCKWISE)  # عدّل الاتجاه إذا لزم
right_motor = Motor(Port.B)

left_sensor  = ColorSensor(Port.C)   # حساس الشمال
right_sensor = ColorSensor(Port.D)   # حساس اليمين

# =========================================================
# 2) أبعاد الروبوت (عدّلها لاحقاً للمعايرة الدقيقة)
# =========================================================
WHEEL_DIAMETER = 62.4
AXLE_TRACK     = 110

robot = DriveBase(left_motor, right_motor, WHEEL_DIAMETER, AXLE_TRACK)
robot.use_gyro(True)  # نفس إعداد برنامج السباق (جيرو مفعّل)

# عتبات دنيا تتجاهل اهتزاز اليد
MIN_DIST = 5  # أقل من 5 مم = ضجيج
MIN_ANG  = 2  # أقل من درجتين = ضجيج

# إعدادات التصحيح الذكي
SEARCH_MARGIN = 50   # هامش بحث إضافي بعد المسافة المجرَّبة (مم)
MIN_SEARCH    = 80   # أدنى مسافة بحث عن الخط
FOLLOW_GAIN   = 2.5  # معامل التحكم P لمتابعة الخط
ALIGN_SPEED   = 25   # سرعة الدوران للمحاذاة (deg/s)

# =========================================================
# 3) سجلات التدريب
# =========================================================
# كل عملية تسجيل تُخزَّن كعنصر رباعي:
#   ("move",   [قطع المسار], آخر مسافة قبل التسجيل, آخر زاوية قبل التسجيل)
#   ("sensor", [أسطر القراءات], None, None)
# قطع المسار: ("turn", زاوية) ("straight", مسافة)
#             ("find_line", (اتجاه, أقصى مسافة)) ("align_line", سرعة)
#             ("follow_line", (مسافة, جانب))
# حفظ "المرجع السابق" داخل العنصر يسمح للتراجع بإعادته بدقة.
actions = []

# كل قياسات الانعكاس (لحساب عتاة الخط تلقائياً)
refl_samples = []

# =========================================================
# 4) دوال مساعدة
# =========================================================
def wait_for_release():
    while hub.buttons.pressed():
        wait(10)

def setup_lines(include_sensors):
    # مقدمة البرنامج الناتج. تُضاف تهيئة الحساسين إذا سُجّلت قراءات أو نقاط ذكية،
    # حتى لا يفشل برنامج السباق عند تشغيله بدون حساسات.
    lines = [
        "from pybricks.hubs import PrimeHub",
        "from pybricks.pupdevices import Motor, ColorSensor",
        "from pybricks.parameters import Port, Direction",
        "from pybricks.robotics import DriveBase",
        "from pybricks.tools import wait",
        "",
        "hub = PrimeHub()",
        "left_motor  = Motor(Port.A, Direction.COUNTERCLOCKWISE)",
        "right_motor = Motor(Port.B)",
    ]
    if include_sensors:
        lines += [
            "left_sensor  = ColorSensor(Port.C)",
            "right_sensor = ColorSensor(Port.D)",
        ]
    lines += [
        "robot = DriveBase(left_motor, right_motor, " + str(WHEEL_DIAMETER) + ", " + str(AXLE_TRACK) + ")",
        "robot.use_gyro(True)",
        "# تسارع/تباطؤ محدود = حركة أنعم بلا انتفاضة عند البداية والتوقف",
        "robot.settings(straight_acceleration=" + str(MOVE_ACCEL)
            + ", turn_acceleration=" + str(MOVE_TURN_ACCEL) + ")",
        "robot.reset()",
    ]
    return lines

def estimated_threshold():
    # عتاة الخط = منتصف المسافة بين أفتح قياس (خلفية) وأظلم قياس (خط)
    if len(refl_samples) >= 2:
        lo, hi = min(refl_samples), max(refl_samples)
        if hi - lo >= 20:
            return (hi + lo) // 2
    return None

def smart_helpers_lines():
    # دوال التصحيح الذكي تُدرج في البرنامج الناتج عند وجود نقاط ذكية.
    #
    # ملاحظة ذاكرة (سبب الخطأ السابق):
    #   كانت هذه الدالة تحتفظ بقالب واحد كبير (~1.6KB) كثابت في الكود،
    #   ثم تستدعي str.replace() ثلاث مرات — وكل استدعاء يخصّص نسخة كاملة
    #   جديدة من القالب. ذاكرة الهاب في PrimeHub محدودة جدًا، فكان يفشل
    #   الطلب بـ MemoryError: "allocating 1569 bytes" وينتهي البرنامج كله.
    #   الحل: نبني الأسطر كقوائم نصوص قصيرة تُخصَّص واحدة واحدة، بلا قالب
    #   كبير وبلا replace — ولن يُطلب أي كتلة كبيرة مرة أخرى.
    th = estimated_threshold()
    if th is None:
        th_line = "LINE_THRESHOLD = 30  # عتاة الخط - عايِرها: قِس فوق الخط وفوق الخلفية بزر LEFT"
    else:
        th_line = ("LINE_THRESHOLD = " + str(th) + "  # محسوبة من قياساتك"
                   + " (الخط ≈ " + str(min(refl_samples)) + "، الخلفية ≈ " + str(max(refl_samples)) + ")")
    return [
        "# --- دوال التصحيح الذكي بالحساسات ---",
        th_line,
        "",
        "def find_line(direction=1, max_dist=250, speed=80):",
        "    # يتحرك ببطء حتى يكشف أحد الحساسين خطاً ثم يتوقف (أدقّ من المسار المفتوح)",
        "    robot.reset()",
        "    robot.drive(direction * speed, 0)",
        "    while abs(robot.distance()) < max_dist:",
        "        if left_sensor.reflection() < LINE_THRESHOLD or right_sensor.reflection() < LINE_THRESHOLD:",
        "            robot.stop()",
        "            return True",
        "        wait(10)",
        "    robot.stop()",
        "    return False",
        "",
        "def align_on_line(speed=" + str(ALIGN_SPEED) + ", max_angle=45):",
        "    # يدور في مكانه حتى يستوي كلا الحساسين فوق الخط (تصحيح الاتجاه)",
        "    robot.reset()",
        "    robot.drive(0, speed)",
        "    while abs(robot.angle()) < max_angle:",
        "        if left_sensor.reflection() < LINE_THRESHOLD and right_sensor.reflection() < LINE_THRESHOLD:",
        "            robot.stop()",
        "            return True",
        "        wait(10)",
        "    robot.stop()",
        "    return False",
        "",
        'def follow_line(dist, side="L", speed=90):',
        "    # يتبع حافة الخط بتحكم P لمسافة dist مم (side = الحساس الذي يتبع الحافة)",
        '    s = left_sensor if side == "L" else right_sensor',
        '    sign = 1 if side == "L" else -1',
        "    robot.reset()",
        "    while robot.distance() < dist:",
        "        error = s.reflection() - LINE_THRESHOLD",
        "        robot.drive(speed, sign * (" + str(FOLLOW_GAIN) + ") * error)",
        "        wait(10)",
        "    robot.stop()",
    ]

def format_seg(seg):
    kind, val = seg
    if kind == "turn":
        return "robot.turn(" + str(val) + ")"
    if kind == "straight":
        return "robot.straight(" + str(val) + ")"
    if kind == "find_line":
        direction, max_dist = val
        return "find_line(" + str(direction) + ", " + str(max_dist) + ")"
    if kind == "align_line":
        return "align_on_line(" + str(val) + ")"
    if kind == "follow_line":
        dist, side = val
        return "follow_line(" + str(dist) + ', "' + side + '")'
    return "# ? " + str(kind) + "=" + str(val)

def merged_moves():
    # يدمج الحركات المتتالية من نفس النوع فقط (turn + turn مثلاً).
    # القطع الذكية تبقى كما هي لأنها معالم مستقلة على المسار.
    merged = []
    for kind, content, _, _ in actions:
        if kind != "move":
            continue
        for seg in content:
            if seg[0] in ("turn", "straight") and merged and merged[-1][0] == seg[0]:
                merged[-1] = (seg[0], merged[-1][1] + seg[1])
            else:
                merged.append((seg[0], seg[1]))
    return merged

def print_full_program():
    # زر واحد يطبع برنامج سباق ذكياً كاملاً جاهزاً للنسخ
    # كل ما يُطبع هنا كود صحيح أو تعليق - يمكن نسخ المخرجات كاملة بأمان
    n_cmds = 0
    include_sensors = False
    include_helpers = False
    for kind, content, _, _ in actions:
        if kind == "move":
            n_cmds += len(content)
            for seg in content:
                if seg[0] in ("find_line", "align_line", "follow_line"):
                    include_helpers = True
                    include_sensors = True
        else:
            include_sensors = True

    # علامتان يلتقط التطبيق ما بينهما ويحوّله إلى ملف .py جاهز للتنزيل.
    # لا تظهران في السجل (التطبيق يخفيهما) ولا تؤثران على الكود.
    print("#@@PROGRAM_BEGIN@@")
    print("")
    print("# " + "=" * 50)
    print("# برنامج السباق الذكي (" + str(n_cmds) + " أمر مسجّل)")
    print("# ناتج آلي من as3_app.py — نزّله من التطبيق كملف .py أو انسخه")
    print("# " + "=" * 50)
    for line in setup_lines(include_sensors):
        print(line)
    if include_helpers:
        for line in smart_helpers_lines():
            print(line)
    print("")
    print("# --- المسار (برنامج واحد؛ أضف run_2() للتكوينات الأخرى")
    print("#     واستدعِها حسب قراءات الحساسات في بداية التشغيل) ---")
    print("def run():")
    printed = False
    for seg in merged_moves():
        if seg[0] in ("turn", "straight") and seg[1] == 0:
            continue  # قطعان متعاكسان أُلغيَا
        print("    " + format_seg(seg))
        printed = True
    if not printed:
        print("    pass")
    print("")
    print("run()")
    print("# --- نهاية المسار ---")

    if include_sensors:
        print("#")
        print("# --- ملاحظات المعايرة: قراءات الحساسات أثناء التدريب ---")
        for kind, content, _, _ in actions:
            if kind == "sensor":
                for line in content:
                    print(line)
        if refl_samples:
            print("# عيّنات الانعكاس: الأقل=" + str(min(refl_samples)) + "، الأعلى=" + str(max(refl_samples)))
            th = estimated_threshold()
            if th is not None:
                print("# عتاة الخط المقترحة = " + str(th))
    print("#@@PROGRAM_END@@")

def print_sensor(name, s):
    c = s.color()
    r = s.reflection()
    a = s.ambient()
    hsv = s.hsv()
    line = "# " + name + ": color=" + str(c) + ", reflection=" + str(r) + ", ambient=" + str(a) + ", hsv=" + str(hsv)
    print(line)
    return line, r

# =========================================================
# 5) أفعال الأزرار / أوامر التطبيق
#   كل فعل كان داخل حلقة الأزرار أصبح دالة مستقلة، حتى يستطيع
#   زر الروبوت وأمر التطبيق استدعاء نفس الفعل تماماً.
# =========================================================
last_distance = 0
last_heading = 0

# تسجيل مدخل stdin للاستطلاع دون حظر (non-blocking)
app_input = poll()
app_input.register(stdin)

# ---------------------------------------------------------
# التحكم عن بعد من تطبيق الويب (أزرار الأسهم في app/index.html)
#   الأحرف: w=للأمام s=للخلف a=لف يسارًا d=لف يمينًا x=إيقاف
#   الفكرة: التطبيق يكرر الأمر كل ~250ms ما دام الزر مضغوطًا،
#   والحلقة هنا تنفّذ خطوة صغيرة في كل دورة. إذا توقفت التكرارات
#   (قطع اتصال / نسيان إصبع / خروج من الصفحة) يتباطأ الروبوت
#   ويتوقف تلقائيًا — أي أن أمان الحركة مبنيّ في البروتوكول.
#
# النعومة: بدل القفز من 0 إلى السرعة الكاملة، نقترب من الهدف بمقدار
# محدود في كل دورة (تسارع محدود RC_ACCEL) — فلا تنتفض الحركة ولا
# تتوقف فجأة، ويصبح الإيقاف تباطؤًا قصيرًا (~0.2 ثانية).
# ---------------------------------------------------------
RC_SPEED   = 120  # مم/ث للدفع الأمامي/الخلفي — عدّله حسب روبوتك
RC_TURN    = 90   # درجة/ث للدوران في المكان
                 # (موجب = يمين/مع عقارب الساعة، سالب = يسار — انظر handle_app_command)
RC_ACCEL      = 900   # مم/ث²     — تسارع/تباطؤ القيادة (أعلى = أسرع استجابة)
RC_TURN_ACCEL = 1200  # درجة/ث²   — تسارع/تباطؤ الدوران
RC_FRAMES  = 20   # دورات الحلقة (~30-40ms للدورة) قبل الإيقاف التلقائي
                 # ≈ 600-800ms: تحمّل تأخّر البلوتوث البسيط حتى لا يتقطّع
                 # الدفع (التطبيق يعيد الأمر كل 250ms)، ولا يزال يوقف
                 # الروبوت سريعًا إذا انقطع الاتصال فعلًا.

# تسارع الحركات في برنامج السباق الناتج (نعومة أثناء التشغيل)
MOVE_ACCEL      = 1200
MOVE_TURN_ACCEL = 1500

rc_frames  = 0    # العدّاد التنازلي للأمان
rc_target_speed = 0   # الهدف المطلوب من التطبيق
rc_target_turn  = 0
rc_speed   = 0.0  # السرعة الحالية (تتحرك تدريجيًا نحو الهدف)
rc_turn    = 0.0
rc_driving = False

def _approach(cur, target, step):
    # خطوة واحدة نحو الهدف بمقدار أقصاه step
    if cur < target:
        return min(cur + step, target)
    if cur > target:
        return max(cur - step, target)
    return cur

def rc_drive(speed, turn):
    # يبدأ/يجدّد حركة عن بعد؛ تُجدَّد من التطبيق بينما الزر مضغوط
    global rc_frames, rc_target_speed, rc_target_turn, rc_driving
    rc_frames = RC_FRAMES
    rc_target_speed = speed
    rc_target_turn = turn
    if not rc_driving:
        hub.speaker.beep(300, 40)
        rc_driving = True

def rc_halt():
    # طلب إيقاف ناعم: يُصفّر الهدف ويكمل rc_tick التباطؤ ثم يحرّر المحركات
    global rc_frames, rc_target_speed, rc_target_turn
    rc_frames = 0
    rc_target_speed = 0
    rc_target_turn = 0

def rc_release():
    # تحرير المحركات (coast) ليُدفع الروبوت باليد بعده مباشرة
    global rc_driving, rc_speed, rc_turn
    rc_driving = False
    rc_speed = 0
    rc_turn = 0
    left_motor.stop()
    right_motor.stop()

def rc_stop():
    # إيقاف فوري بلا تباطؤ — للطوارئ وعند إغلاق البرنامج فقط
    global rc_frames, rc_target_speed, rc_target_turn
    if rc_driving:
        hub.speaker.beep(250, 40)
    rc_frames = 0
    rc_target_speed = 0
    rc_target_turn = 0
    rc_release()

def rc_tick():
    # خطوة واحدة: نقترب من الهدف بتسارع محدود، ثم تباطؤ تلقائي عند انتهاء المهلة
    global rc_frames, rc_speed, rc_turn, rc_target_speed, rc_target_turn
    if rc_frames > 0:
        rc_frames -= 1
    elif rc_target_speed or rc_target_turn:
        rc_target_speed = 0
        rc_target_turn = 0

    if not rc_driving:
        return

    rc_speed = _approach(rc_speed, rc_target_speed, RC_ACCEL * 0.03)
    rc_turn  = _approach(rc_turn,  rc_target_turn,  RC_TURN_ACCEL * 0.03)

    # وصلنا للسكون والهدف صفر → حرّر المحركات
    if rc_target_speed == 0 and rc_target_turn == 0 and abs(rc_speed) < 4 and abs(rc_turn) < 6:
        rc_release()
        return

    robot.drive(int(rc_speed), int(rc_turn))

def rc_halt_and_wait():
    # يوقف الدفع بنعومة، وينتظر السكون التام قبل أي أمر تدريب
    rc_halt()
    n = 0
    while rc_driving and n < 25:   # حتى ~0.5 ثانية كحد أقصى
        rc_tick()
        wait(20)
        n += 1
    if rc_driving:
        rc_stop()

# ---------------------------------------------------------
# إرسال الكود من التطبيق وتنفيذه على الروبوت
#
#   قبل هذه الميزة كان تشغيل برنامج السباق يحتاج تنزيل ملف .py ثم فتحه
#   في Pybricks Code وتشغيله. الآن يستطيع التطبيق إرسال الكود نفسه إلى
#   الـ Hub: يبدأ بحرف K ثم أسطر قصيرة (سطر لكل أمر) ثم حرف E، ويليه
#   حرف G للتنفيذ — أو يبقى الكود محفوظًا في الـ Hub حتى يُطلب G.
#
#   صيغة السطر الواحد (نفس أوامر برنامج السباق، بلا أقواس):
#     T <زاوية>            → robot.turn
#     S <مسافة>            → robot.straight
#     F <اتجاه> <مسافة>     → find_line
#     A <سرعة>             → align_on_line
#     L <مسافة> <L|R>      → follow_line
#
#   التنفيذ لا يستخدم دوال Pybricks الحاجزة (straight/turn) بل يتقدّم
#   دفعة صغيرة في كل دورة من الحلقة الرئيسية، فيبقى الروبوت يستقبل
#   حرف x (إيقاف) من التطبيق، ويستجيب لأي زر على الهاب في أي لحظة.
# ---------------------------------------------------------
RUN_SPEED        = 220    # مم/ث   — سرعة القطع المستقيم
RUN_TURN_RATE    = 130    # درجة/ث — سرعة الدوران
RUN_SEARCH_SPEED = 80     # مم/ث   — سرعة البحث عن الخط
RUN_FOLLOW_SPEED = 90     # مم/ث   — سرعة متابعة الخط
RUN_TOL_DIST     = 4      # مم     — سماحية الوصول للمسافة
RUN_TOL_ANG      = 2      # درجة   — سماحية الوصول للزاوية
RUN_ALIGN_MAX    = 45     # درجة   — أقصى دوران لمحاذاة الخط
RUN_MAX_MS       = 120000 # أمان: أقصى مدة تنفيذ، يُلغى بعدها تلقائيًا
RUN_MAX_LINES    = 160    # أقصى عدد أوامر يُستلم من التطبيق
RUN_MAX_LINE_LEN = 40     # أقصى طول سطر مستلم (حماية للذاكرة)

code_mode    = False  # هل نحن في منتصف استلام الكود؟
code_line    = ""     # السطر الجاري تجميعه
code_new     = []     # المقاطع المستلمة (تُبنى سطرًا بسطر لتوفير الذاكرة)
code_skipped = 0      # أسطر لم تُفهم أو تجاوزت الحد

run_queue  = []      # الأوامر الجاهزة للتنفيذ (مقاطع)
run_active = False   # هل يجري تنفيذ الكود الآن؟
run_index  = 0       # رقم المقطع الجاري
run_phase  = "start" # "start" = تهيئة المقطع، "go" = تنفيذه
run_goal_d = 0       # هدف المسافة للمقطع الحالي
run_goal_h = 0       # هدف الزاوية للمقطع الحالي
run_base_d = 0       # مسافة البداية للمقطع الحالي
run_base_h = 0       # زاوية البداية للمقطع الحالي
run_th     = 30      # عتاة الخط المستخدمة أثناء التنفيذ
run_watch  = StopWatch()

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def seg_label(seg):
    # نفس شكل السطر في برنامج السباق — ليظهر السجل مفهومًا
    kind = seg[0]
    if kind == "turn":
        return "robot.turn(" + str(seg[1]) + ")"
    if kind == "straight":
        return "robot.straight(" + str(seg[1]) + ")"
    if kind == "find_line":
        return "find_line(" + str(seg[1]) + ", " + str(seg[2]) + ")"
    if kind == "align_line":
        return "align_on_line(" + str(seg[1]) + ")"
    if kind == "follow_line":
        return "follow_line(" + str(seg[1]) + ', "' + str(seg[2]) + '")'
    return str(kind)

def parse_code_line(line):
    # يحوّل سطرًا قصيرًا من التطبيق إلى مقطع تنفيذ، أو None إن لم يُفهم
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        k = parts[0]
        if k == "T":
            return ("turn", int(float(parts[1])))
        if k == "S":
            return ("straight", int(float(parts[1])))
        if k == "F" and len(parts) >= 3:
            return ("find_line", int(float(parts[1])), int(float(parts[2])))
        if k == "A":
            return ("align_line", int(float(parts[1])))
        if k == "L" and len(parts) >= 3:
            side = "R" if parts[2].upper()[:1] == "R" else "L"
            return ("follow_line", int(float(parts[1])), side)
    except (ValueError, IndexError):
        return None
    return None

def code_take_line():
    # ينهي السطر الجاري ويحوّله فورًا إلى مقطع تنفيذ.
    # لا نحتفظ بنصوص الأسطر كلها (ذاكرة الهاب محدودة) بل بالمقاطع فقط.
    global code_line, code_skipped
    line = code_line
    code_line = ""
    if not line:
        return
    if len(code_new) >= RUN_MAX_LINES:
        code_skipped += 1
        return
    seg = parse_code_line(line)
    if seg is None:
        code_skipped += 1
    else:
        code_new.append(seg)

def code_receive_start():
    # K: بداية استلام كود جديد (يُلغي التنفيذ الجاري أولًا)
    global code_mode, code_line, code_new, code_skipped
    if run_active:
        run_cancel("استلام كود جديد")
    code_mode = True
    code_line = ""
    code_new = []
    code_skipped = 0
    print("# 📥 استلام الكود من التطبيق…")

def code_receive_finish():
    # E: نهاية الاستلام — المقاطع المستلمة تصبح قائمة التنفيذ
    global code_mode, code_new, code_skipped, run_queue
    code_take_line()          # آخر سطر إن لم ينتهِ بسطر جديد
    code_mode = False

    n = len(code_new)
    skipped = code_skipped
    if not n:
        print("# ⚠ لم يصل أي أمر صالح — أبقيت الكود السابق كما هو")
        hub.speaker.beep(250, 250)
        code_new = []
        return

    run_queue = code_new
    code_new = []
    msg = "# ✓ استُلم الكود: " + str(n) + " أمرًا"
    if skipped:
        msg += " (تجاهلت " + str(skipped) + " سطرًا)"
    print(msg)
    hub.speaker.beep(900, 120)

def resync_tracking():
    # بعد التشغيل: نُعيد نقطة القياس إلى موضع الروبوت الحالي
    # حتى لا يُسجَّل مسار التنفيذ كأنه حركة يدوية في التسجيل التالي
    global last_distance, last_heading
    last_distance = robot.distance()
    last_heading = hub.imu.heading()

def _run_end(msg, freq):
    global run_active
    robot.stop()
    run_active = False
    resync_tracking()
    print(msg)
    hub.speaker.beep(freq, 200)

def run_start():
    # G: تنفيذ الكود المستلم الآن
    global run_active, run_index, run_phase, run_th
    if not run_queue:
        print("# ⚠ لا يوجد كود على الهاب — أرسله من التطبيق أولًا")
        hub.speaker.beep(250, 250)
        return
    if run_active:
        return
    rc_halt_and_wait()          # لا نبدأ والروبوت يتحرك عن بعد
    run_active = True
    run_index = 0
    run_phase = "start"
    run_th = estimated_threshold()
    if run_th is None:
        run_th = 30
    run_watch.reset()
    print("# ▶ بدء تنفيذ الكود (" + str(len(run_queue)) + " أمر) — عتاة الخط = " + str(run_th))
    print("#   للإيقاف: x من التطبيق أو أي زر على الهاب")
    hub.speaker.beep(1000, 200)

def run_cancel(reason):
    if not run_active:
        robot.stop()
        return
    _run_end("# ⏹ أُلغي تنفيذ الكود — " + reason, 300)

def run_finish():
    _run_end("# ✓ انتهى تنفيذ الكود بنجاح", 800)

def _run_step_straight(dist):
    global run_phase, run_goal_d
    if run_phase == "start":
        run_goal_d = robot.distance() + dist
        run_phase = "go"
        return False
    rem = run_goal_d - robot.distance()
    if abs(rem) <= RUN_TOL_DIST:
        robot.stop()
        return True
    spd = int(_clamp(abs(rem) * 4, 45, RUN_SPEED))
    robot.drive(spd if rem > 0 else -spd, 0)
    return False

def _run_step_turn(angle):
    global run_phase, run_goal_h
    if run_phase == "start":
        # اتجاه الـ IMU مستمر (لا يلتف عند 180) وموجبه مع عقارب الساعة،
        # وهو نفس اتجاه robot.turn — فالمقارنة مباشرة.
        run_goal_h = hub.imu.heading() + angle
        run_phase = "go"
        return False
    err = run_goal_h - hub.imu.heading()
    if abs(err) <= RUN_TOL_ANG:
        robot.stop()
        return True
    rate = int(_clamp(abs(err) * 5, 30, RUN_TURN_RATE))
    robot.drive(0, rate if err > 0 else -rate)
    return False

def _run_step_find(direction, max_dist):
    global run_phase, run_base_d
    if run_phase == "start":
        run_base_d = robot.distance()
        run_phase = "go"
        return False
    if left_sensor.reflection() < run_th or right_sensor.reflection() < run_th:
        robot.stop()
        return True
    if abs(robot.distance() - run_base_d) >= max_dist:
        robot.stop()
        return True
    robot.drive(RUN_SEARCH_SPEED if direction >= 0 else -RUN_SEARCH_SPEED, 0)
    return False

def _run_step_align(speed):
    global run_phase, run_base_h
    if run_phase == "start":
        run_base_h = hub.imu.heading()
        run_phase = "go"
        return False
    if left_sensor.reflection() < run_th and right_sensor.reflection() < run_th:
        robot.stop()
        return True
    if abs(hub.imu.heading() - run_base_h) >= RUN_ALIGN_MAX:
        robot.stop()
        return True
    robot.drive(0, speed)
    return False

def _run_step_follow(dist, side):
    global run_phase, run_base_d
    if run_phase == "start":
        run_base_d = robot.distance()
        run_phase = "go"
        return False
    if abs(robot.distance() - run_base_d) >= dist:
        robot.stop()
        return True
    s = left_sensor if side == "L" else right_sensor
    sign = 1 if side == "L" else -1
    robot.drive(RUN_FOLLOW_SPEED, int(sign * FOLLOW_GAIN * (s.reflection() - run_th)))
    return False

def run_tick():
    # خطوة واحدة من تنفيذ الكود — تُنادى من الحلقة الرئيسية كل دورة
    global run_active, run_index, run_phase
    if not run_active:
        return
    if run_watch.time() > RUN_MAX_MS:
        run_cancel("تجاوز مدة الأمان")
        return
    if run_index >= len(run_queue):
        run_finish()
        return

    seg = run_queue[run_index]
    if run_phase == "start":
        print("# " + str(run_index + 1) + "/" + str(len(run_queue)) + "  " + seg_label(seg))

    kind = seg[0]
    if kind == "straight":
        done = _run_step_straight(seg[1])
    elif kind == "turn":
        done = _run_step_turn(seg[1])
    elif kind == "find_line":
        done = _run_step_find(seg[1], seg[2])
    elif kind == "align_line":
        done = _run_step_align(seg[1])
    elif kind == "follow_line":
        done = _run_step_follow(seg[1], seg[2])
    else:
        done = True

    if done:
        run_index += 1
        run_phase = "start"

# ---------------------------------------------------------
# قراءة الحساسات تلقائيًا مع الحركة (بدل الضغط على LEFT/L)
#   - تُجمع العينات دائمًا في الخلفية (تُحسّن حساب عتبة الخط).
#   - ويُبثّ سطر قياس في السجل أثناء الحركة فقط (بالأسهم أو باليد).
#   - الأمر y يفعّل البث، و z يوقفه (من مفتاح التطبيق).
# ---------------------------------------------------------
AUTO_SAMPLE_EVERY = 3     # كل 3 دورات ≈ 100ms
AUTO_STREAM       = True  # بثّ القراءات في السجل أثناء الحركة
SAMPLE_MAX        = 400   # أقصى عدد عينات محفوظة لحساب العتبة
MOVE_EPS_DIST     = 8     # مم — أقل من ذلك يُعدّ سكونًا (يد)
MOVE_EPS_ANG      = 3     # درجة

auto_tick = 0
watch_d = 0
watch_h = 0

def sample_sensors():
    # يقرأ الحساسين ويضيف العينة (الأظلم منهما) لقائمة المعايرة
    l = left_sensor.reflection()
    r = right_sensor.reflection()
    refl_samples.append(min(l, r))
    while len(refl_samples) > SAMPLE_MAX:
        refl_samples.pop(0)
    return l, r

def auto_read_tick():
    # تُنادى كل دورة من الحلقة الرئيسية؛ تقرأ كل ~100ms
    global auto_tick, watch_d, watch_h
    auto_tick += 1
    if auto_tick < AUTO_SAMPLE_EVERY:
        return
    auto_tick = 0

    l, r = sample_sensors()
    d = robot.distance()
    h = hub.imu.heading()
    hand_moved = abs(d - watch_d) >= MOVE_EPS_DIST or abs(h - watch_h) >= MOVE_EPS_ANG
    watch_d = d
    watch_h = h

    # أثناء تنفيذ الكود لا نبثّ سطر قياس لكل خطوة (لئلا يمتلئ السجل)،
    # فالتطبيق يعرض تقدّم التنفيذ سطرًا لكل مقطع.
    if AUTO_STREAM and not run_active and (rc_driving or hand_moved):
        # سطر مضغوط: d=المسافة h=الاتجاه L/R=الانعكاس
        print("# T d=" + str(int(d)) + " h=" + str(int(h))
              + " L=" + str(l) + " R=" + str(r))

def do_undo():
    global last_distance, last_heading
    # تراجع: يحذف كل ما أضافته آخر ضغطة دفعة واحدة ويعيد المرجع السابق
    if actions:
        kind, content, prev_dist, prev_head = actions.pop()
        if kind == "move":
            for seg in content:
                print("# حذف: " + format_seg(seg))
            # إرجاع نقطة القياس حتى يمكن إعادة تسجيل نفس الحركة
            last_distance = prev_dist
            last_heading = prev_head
        else:
            print("# حذف قراءات الحساسات الأخيرة")
    else:
        print("# لا يوجد ما يُحذف")
    hub.speaker.beep(400, 150)

def do_find_line_point():
    global last_distance, last_heading
    # نقطة خط ذكية: تستبدل الحركة منذ آخر تسجيل ببحث دقيق عن الخط،
    # وتضيف محاذاة إذا كان الحسّاسان فوق الخط الآن.
    curr_distance = robot.distance()
    curr_heading = hub.imu.heading()
    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading

    l = left_sensor.reflection()
    r = right_sensor.reflection()
    refl_samples.append(min(l, r))

    segs = []
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))

    direction = 1 if diff_dist >= 0 else -1
    max_dist = max(int(round(abs(diff_dist))) + SEARCH_MARGIN, MIN_SEARCH)
    segs.append(("find_line", (direction, max_dist)))

    th = estimated_threshold()
    if th is None:
        th = 30  # نفس القيمة الافتراضية في البرنامج الناتج
    if l < th and r < th:
        segs.append(("align_line", ALIGN_SPEED))

    actions.append(("move", segs, last_distance, last_heading))
    for seg in segs:
        print(format_seg(seg))
    last_distance = curr_distance
    last_heading = curr_heading
    hub.speaker.beep(500, 80)

def do_follow_line_seg():
    global last_distance, last_heading
    # مقطع متابعة خط: يتبع الحافة بالمسافة المجرَّبة منذ آخر تسجيل
    curr_distance = robot.distance()
    curr_heading = hub.imu.heading()
    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading

    l = left_sensor.reflection()
    r = right_sensor.reflection()
    refl_samples.append(min(l, r))

    segs = []
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))

    if abs(diff_dist) >= MIN_DIST:
        side = "L" if l <= r else "R"
        segs.append(("follow_line", (int(round(abs(diff_dist))), side)))

    if segs:
        actions.append(("move", segs, last_distance, last_heading))
        for seg in segs:
            print(format_seg(seg))
        last_distance = curr_distance
        last_heading = curr_heading
        hub.speaker.beep(550, 80)
    else:
        print("# حركة أصغر من العتبة - تم تجاهلها")

def do_record_move():
    global last_distance, last_heading
    curr_distance = robot.distance()
    curr_heading = hub.imu.heading()

    diff_dist = curr_distance - last_distance
    diff_head = curr_heading - last_heading  # درجات (موجب = مع عقارب الساعة)

    did_straight = False
    did_turn = False
    segs = []

    # الدوران أولاً ثم المستقيم (ترتيب "نقطة الطريق": وجّه ثم سِر)
    if abs(diff_head) >= MIN_ANG:
        segs.append(("turn", int(round(diff_head))))
        did_turn = True
    if abs(diff_dist) >= MIN_DIST:
        segs.append(("straight", int(round(diff_dist))))
        did_straight = True

    if segs:
        # نحفظ المرجع السابق داخل العنصر حتى يستعيده التراجع
        actions.append(("move", segs, last_distance, last_heading))
        for seg in segs:
            print(format_seg(seg))
        last_distance = curr_distance
        last_heading = curr_heading
        if did_turn:
            hub.speaker.beep(800, 80)
        if did_straight:
            hub.speaker.beep(600, 80)
    else:
        print("# حركة أصغر من العتبة - تم تجاهلها")

def do_read_sensors():
    l_line, l_ref = print_sensor("LEFT sensor (Port.C)", left_sensor)
    r_line, r_ref = print_sensor("RIGHT sensor (Port.D)", right_sensor)
    actions.append(("sensor", [l_line, r_line], None, None))
    refl_samples.append(min(l_ref, r_ref))
    hub.speaker.beep(750, 80)

def do_print_program():
    try:
        print_full_program()
    except MemoryError:
        # فشل الذاكرة أثناء الطباعة: نغلق علامات الالتقاط حتى لا تبقى
        # لوحة التطبيق معلّقة على نص ناقص، ونشرح ما حدث بدل انتهاء البرنامج
        print("#@@PROGRAM_END@@")
        print("# ⚠ نفد ذاكرة الهاب: لم يكتمل طباعة البرنامج")
        print("#   احذف بعض التسجيلات (U) ثم اضغط طباعة مرة أخرى (C)")
        hub.speaker.beep(250, 250)
        return
    hub.speaker.beep(900, 150)

def handle_app_command(cmd):
    # حرف واحد من التطبيق = نفس ضغطة الزر المقابلة على الروبوت
    global AUTO_STREAM, code_mode, code_line

    # --- استلام الكود من التطبيق: كل ما بين K و E أسطر نصية ---
    if code_mode:
        if cmd == "\n":
            code_take_line()
        elif cmd == "E" and not code_line:
            # نهاية الإرسال — يصل E في بداية سطر جديد (أي أن السطر السابق اكتمل)
            code_receive_finish()
        elif cmd != "\r" and len(code_line) < RUN_MAX_LINE_LEN:
            code_line += cmd
        return
    if cmd == "K":
        code_receive_start()
        return
    if cmd == "E":
        code_receive_finish()
        return
    if cmd == "G":
        run_start()
        return

    # --- إيقاف: تنفيذ كود جارٍ أو تحرير المحركات ---
    if cmd == "x":
        if run_active:
            run_cancel("من التطبيق")
        else:
            rc_halt()                    # تباطؤ ناعم ثم تحرير المحركات
        return

    # أي أمر آخر أثناء تنفيذ الكود = إيقافه فورًا (أمان)
    if run_active and cmd != "y" and cmd != "z":
        run_cancel("أمر جديد من التطبيق")

    # --- قراءة الحساسات التلقائية: y تشغيل / z إيقاف ---
    if cmd == "y":
        AUTO_STREAM = True
        print("# القراءة التلقائية للحساسات: مفعّلة")
        hub.speaker.beep(700, 60)
        return
    if cmd == "z":
        AUTO_STREAM = False
        print("# القراءة التلقائية للحساسات: متوقفة")
        hub.speaker.beep(500, 60)
        return

    # --- أوامر التحكم عن بعد (لا تسجيل، لا طباعة) ---
    if cmd == "w":
        rc_drive(RC_SPEED, 0)
        return
    if cmd == "s":
        rc_drive(-RC_SPEED, 0)
        return
    # ملاحظة اتجاه الدوران: في Pybricks القيمة الموجبة لمعدّل الدوران
    # تعني الدوران يمينًا (مع عقارب الساعة)، والسلبية يسارًا (عكسها).
    # إذا انعكس الاتجاه على روبوتك (تركيب محرك معكوس) اقلب الإشارتين هنا.
    if cmd == "a":                       # لف يسارًا  (عكس عقارب الساعة)
        rc_drive(0, -RC_TURN)
        return
    if cmd == "d":                       # لف يمينًا  (مع عقارب الساعة)
        rc_drive(0, RC_TURN)
        return

    # أي أمر تدريب: أوقف الدفع عن بعد بنعومة حتى لا تتداخل الحركتان
    if rc_driving:
        rc_halt_and_wait()

    if cmd == "R":
        do_record_move()
    elif cmd == "L":
        do_read_sensors()
    elif cmd == "C":
        do_print_program()
    elif cmd == "F":
        do_find_line_point()
    elif cmd == "T":
        do_follow_line_seg()
    elif cmd == "U":
        do_undo()
    # أي حرف آخر (مسافات، أسطر جديدة...) يُتجاهل

# =========================================================
# 6) البرنامج الرئيسي: توليد كود ذكي من التدريب
# =========================================================
for line in setup_lines(False):
    print(line)

left_motor.stop()   # coast: تُترك المحركات حرة ليُدفع الروبوت باليد
right_motor.stop()

robot.reset()  # تصفير عدادات المسافة والزاوية (والجيرو)

last_distance = robot.distance()
last_heading = hub.imu.heading()

hub.light.on(Color.BLUE)
print("")
print("# جاهز: حرّك الروبوت بيدك أو من تطبيق الويب، ثم اضغط للتسجيل")
print("# التطبيق: R تسجيل حركة | L قراءة حساسات | C طباعة البرنامج")
print("#          F نقطة خط ذكية | T متابعة خط | U تراجع")
print("#          أزرار الأسهم: w/s/d/a للتحريك عن بعد (ناعم)، x = إيقاف")
print("#          القراءة التلقائية: y تشغيل | z إيقاف (سطور # T أثناء الحركة)")
print("#          إرسال الكود من التطبيق: K استلام ← أسطر ← E انتهى ← G تنفيذ")
print("#          و x أثناء التنفيذ = إيقافه فورًا")
print("# أزرار الروبوت ما زالت تعمل:")
print("# - RIGHT       : تسجيل حركة (دوران ثم مستقيم)")
print("# - LEFT        : تسجيل قراءات الحساسين (لحساب عتاة الخط)")
print("# - CENTER+LEFT : نقطة خط ذكية find_line (+ محاذاة) بدل آخر مستقيم")
print("# - CENTER+RIGHT: مقطع متابعة خط follow_line بآخر مسافة")
print("# - LEFT+RIGHT  : حذف آخر تسجيل (مع إرجاع نقطة القياس)")
print("# - CENTER      : طباعة برنامج السباق الذكي الكامل")
print("# APP_READY")

try:
    while True:
        # 1) أوامر التطبيق الواصلة عبر البلوتوث (stdin) - دون حظر الحلقة
        while app_input.poll(0):
            ch = stdin.read(1)
            if not ch:
                break
            try:
                handle_app_command(ch)
            except MemoryError:
                # أي أمر آخر نفد فيه الذاكرة: نكمل الحلقة بدل انتهائها
                print("# ⚠ نفد الذاكرة — تجاهل الأمر واستمر")
                hub.speaker.beep(250, 250)

        # 2) أزرار الروبوت الفعلية (نفس أولوية الفحص السابقة)
        #    أي زر يوقف الدفع عن بعد أو تنفيذ الكود أولًا حتى لا يتداخلا
        pressed = hub.buttons.pressed()
        if pressed and rc_driving:
            rc_halt_and_wait()
        if pressed and run_active:
            run_cancel("زر من الهاب")
            wait_for_release()      # لا ننفّذ وظيفة الزر بعد إلغاء التنفيذ
            pressed = ()

        if Button.LEFT in pressed and Button.RIGHT in pressed:
            do_undo()
            wait_for_release()

        elif Button.CENTER in pressed and Button.LEFT in pressed:
            do_find_line_point()
            wait_for_release()

        elif Button.CENTER in pressed and Button.RIGHT in pressed:
            do_follow_line_seg()
            wait_for_release()

        elif Button.RIGHT in pressed:
            do_record_move()
            wait_for_release()

        elif Button.LEFT in pressed:
            do_read_sensors()
            wait_for_release()

        elif Button.CENTER in pressed:
            do_print_program()
            wait_for_release()

        # 3) تنفيذ دورة واحدة من التحكم عن بعد (تسارع محدود + إيقاف تلقائي)
        rc_tick()

        # 3.5) تنفيذ دورة واحدة من الكود المستلم من التطبيق (دفعات صغيرة)
        run_tick()

        # 4) قراءة الحساسات تلقائيًا (جمع عينات + بثّ أثناء الحركة)
        auto_read_tick()

        # أثناء استلام الكود نُسرّع الدورة (10ms) حتى نفرّغ مخزن الإدخال
        # أسرع من وصول الأسطر من التطبيق، فلا يضيع أي حرف
        wait(10 if code_mode else 30)

finally:
    hub.light.on(Color.RED)
    rc_stop()
    left_motor.stop()
    right_motor.stop()
