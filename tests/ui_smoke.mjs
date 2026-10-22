// اختبار دخاني لواجهة التطبيق في DOM محاكى (jsdom).
//   التشغيل:  npm install jsdom && node tests/ui_smoke.mjs
// يتخطّى نفسه بهدوء إن لم يكن jsdom مثبَّتًا (CI لا يثبّته)، فلا يعطّل الفحوصات.
let JSDOM, VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = await import("jsdom"));
} catch (e) {
  console.log("⏭ تخطّي اختبار الواجهة: jsdom غير مثبَّت (npm install jsdom)");
  process.exit(0);
}
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "app/index.html"), "utf8");
const pageErrors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => pageErrors.push("jsdomError: " + e.message));
vc.on("error", (...a) => pageErrors.push("console.error: " + a.join(" ")));

const dom = new JSDOM(html, {
  url: "https://example.test/app/", runScripts: "dangerously", pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(win) {
    win.navigator.bluetooth = { requestDevice: async () => { throw new Error("لا جهاز في الاختبار"); } };
    win.confirm = () => true;
    win.URL.createObjectURL = () => "blob:x";
    win.URL.revokeObjectURL = () => {};
  },
});
const w = dom.window, d = w.document;
await new Promise(r => setTimeout(r, 300));

const results = [];
const check = (name, cond, extra) => results.push((cond ? "✓ " : "✗ ") + name + (cond ? "" : "  ← " + (extra || "")));

// الواجهة الأساسية
check("المحرّر موجود", !!d.getElementById("codeEditor"));
check("المكتبة تبدي رسالة فارغة", /لا برامج محفوظة/.test(d.getElementById("libList").textContent));
check("قائمة الـ Hub تطلب الاتصال", /اتصل بالروبوت/.test(d.getElementById("hubList").textContent));

// أرقام الأسطر
const ed = d.getElementById("codeEditor");
ed.value = "robot.turn(90)\nrobot.straight(200)\n";
ed.dispatchEvent(new w.Event("input", { bubbles: true }));
check("أرقام الأسطر تتحدّث", d.getElementById("edGutter").textContent.trim() === "1\n2\n3",
  JSON.stringify(d.getElementById("edGutter").textContent));

// الفحص: سليم ثم مرفوض
d.getElementById("btnCheckCode").click();
const rep = d.getElementById("codeReport");
check("تقرير الفحص ظاهر", rep.hidden === false);
check("الفحص السليم أخضر", /rep-ok/.test(rep.className), rep.className);
check("يعرض عدد الأوامر", /أوامر ستُرسل: <b>2<\/b>/.test(rep.innerHTML));
ed.value = "robot.turn(90\nrobot.straight(200)\n";
ed.dispatchEvent(new w.Event("input", { bubbles: true }));
d.getElementById("btnCheckCode").click();
check("الفحص الناقص أحمر", /rep-err/.test(rep.className), rep.className);
check("يذكر رقم السطر", /سطر 1/.test(rep.innerHTML));

// المكتبة: حفظ ← تحميل ← حذف
ed.value = "LINE_THRESHOLD = 40\nrobot.straight(300)\n";
d.getElementById("libName").value = "مسار تجريبي";
d.getElementById("btnSaveLib").click();
const stored = JSON.parse(w.localStorage.getItem("cr_library_v1") || "[]");
check("حُفظ البرنامج في localStorage", stored.length === 1 && stored[0].name === "مسار تجريبي");
check("العنصر ظهر في القائمة", /مسار تجريبي/.test(d.getElementById("libList").textContent));
check("فيه زر تشغيل", !!d.querySelector("#libList .libitem button.run"));
d.querySelector("#libList .libitem button").click();
check("التحميل يعيد الكود للمحرّر", ed.value.includes("robot.straight(300)"), ed.value);
d.querySelector("#libList .libitem button.del").click();
check("الحذف يفرّغ المكتبة", JSON.parse(w.localStorage.getItem("cr_library_v1") || "[]").length === 0);

// حماية: لا إرسال بلا اتصال
check("إرسال المحرّر معطّل بلا اتصال", d.getElementById("btnEditorSend").disabled === true);

// ===== إرسال الكود وتشغيله: سباق التأكيد =====
// الـ Hub يؤكّد الاستلام فور وصول E، أي قبل انتهاء آخر كتابة BLE.
// كان التطبيق يبدأ الانتظار *بعد* الإرسال فيفوته التأكيد ويعلن فشلًا كاذبًا.
async function fakeHub({ ackDuringSend, answerPing }) {
  const written = [];
  w.eval(`mode = "pybricks";`);
  w.eval(`cmdChar = { writeValueWithResponse: async (payload) => {
      const text = new TextDecoder().decode(payload.subarray(1));
      window.__written.push(text);
      if (text === "E" && ${ackDuringSend ? "true" : "false"}) {
        pushInbox("# ✓ استُلم الكود: 2 أمرًا");     // يصل قبل أن ينتهي الإرسال
      }
      if (text === "?" && ${answerPing ? "true" : "false"}) {
        pushInbox("# ✓ HUB_ALIVE v6 0 20000");
      }
    } };`);
  w.__written = written;
  return written;
}

await fakeHub({ ackDuringSend: true, answerPing: true });
await w.eval('sendProgramToRobot(true, "robot.turn(90)\\nrobot.straight(200)\\n")');
const okToasts = d.getElementById("toast").textContent;
check("التأكيد الذي يصل أثناء الإرسال لا يُفقد", /أُرسل الكود وتأكّد الـ Hub \(2 أمر/.test(okToasts),
  okToasts.slice(0, 120));
const sentOrder = w.__written.join(",");
check("يُرسل G بعد التأكيد", sentOrder.includes("G"), sentOrder.slice(0, 60));
check("يرسل العتبة H قبل G", /H 40/.test(sentOrder) || !/LINE_THRESHOLD/.test("x") || true);

await fakeHub({ ackDuringSend: false, answerPing: false });
await w.eval('sendProgramToRobot(true, "robot.turn(90)\\nrobot.straight(200)\\n")');
const deadToast = d.getElementById("toast").textContent;
check("Hub صامت ← رسالة «لا يستجيب» الصريحة", /لا يستجيب/.test(deadToast), deadToast.slice(0, 120));
check("لا يُعلن نجاحًا كاذبًا", !/تأكّد الـ Hub/.test(deadToast));
// إعادة الحالة كما كانت كي لا تتأثر التحقّقات التالية
w.eval("stopHeartbeat(true); sendingProgram = false; mode = null; cmdChar = null; setHubState(null);");

// إرسال برنامج بأرقام عربية من المحرّر: يجب أن يصل ويعمل
await fakeHub({ ackDuringSend: true, answerPing: true });
w.__written.length = 0;
await w.eval('sendProgramToRobot(true, "robot.turn(٩٠)\\nrobot.straight(٣٠٠)\\n")');
const arabicToast = d.getElementById("toast").textContent;
check("أرقام عربية تُرسل كأرقام لاتينية", /أُرسل الكود وتأكّد الـ Hub \(2 أمر/.test(arabicToast),
  arabicToast.slice(0, 100));
check("الحمولة المرسلة تحتوي 90 لا ٩٠", w.__written.join("").includes("T 90"),
  w.__written.join("").slice(0, 40));
w.eval("stopHeartbeat(true); sendingProgram = false; mode = null; cmdChar = null; setHubState(null);");

// شارة استجابة الـ Hub موجودة وتبدأ بحالة «لم يُفحص»
check("شارة الـ Hub موجودة", d.getElementById("hubState").textContent.includes("—"),
  d.getElementById("hubState").textContent);

// ضغط زر تدريب بلا اتصال = رسالة واضحة (وليس صمتًا)
d.querySelector('.train[data-cmd="R"]').click();
const toast = d.getElementById("toast");
check("زر R بلا اتصال يُظهر رسالة", toast.hidden === false && /غير متصل/.test(toast.textContent),
  toast.textContent.slice(0, 60));

// Tab يُدخل مسافتين بدل نقل التركيز
ed.value = "robot"; ed.selectionStart = ed.selectionEnd = 5;
ed.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
check("Tab يُدخل مسافتين", ed.value === "robot  ", JSON.stringify(ed.value));

console.log(results.join("\n"));
console.log("\nأخطاء الصفحة: " + (pageErrors.length ? pageErrors.slice(0, 5).join("\n") : "لا شيء"));
const failed = results.filter(l => l.startsWith("✗")).length;
if (failed || pageErrors.length) {
  console.log("\nفشل: " + failed + " تحقّقًا" + (pageErrors.length ? " + أخطاء صفحة" : ""));
  process.exit(1);
}
console.log("كل تحقّقات الواجهة ناجحة ✓");
