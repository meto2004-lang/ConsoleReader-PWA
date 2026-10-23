/* ConsoleReader — Service Worker
   الهدف: أن تفتح الصفحة في الميدان حتى بلا إنترنت، وتتحدّث تلقائيًا عند توفر اتصال.
   كل المسارات نسبية لأن الصفحة قد تُقدَّم من مسار فرعي (GitHub Pages: /<repo>/app/).

   ملاحظة مهمة (خطأ سابق): طلبات التنقّل (navigate) تُخدَم من النسخة المخزّنة
   تحت "./index.html"، بينما كان التحديث يُكتب تحت عنوان الطلب نفسه ("/app/").
   النتيجة أن نسخة الصفحة المخزّنة لم تُستبدل أبدًا، فبقي المستخدمون المثبَّتون
   على نسخة قديمة مهما رُفع تحديث — ما لم يتغيّر هذا الملف نفسه.
   الحل: كل تنقّل يحدّث أيضًا مفتاح "./index.html"، مع ترقية اسم الذاكرة في كل
   إصدار كشبكة أمان ثانية.
*/

const CACHE = "consolereader-v10";

const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png"
];

// التثبيت: نخزّن كل ما تحتاجه الصفحة حتى تعمل دون إنترنت.
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

// التفعيل: نحذف ذاكرة النسخ القديمة حتى لا تتراكم.
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

/* الجلب: من الذاكرة أولًا (يعمل دون إنترنت)، مع تحديث في الخلفية (stale-while-revalidate).
   طلبات التنقّل تُخدم بصفحة التطبيق دائمًا — حتى لو طُلب مسار غير موجود. */
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const isNavigate = e.request.mode === "navigate";
  const cachedKey = isNavigate ? "./index.html" : e.request;
  e.respondWith(respond(cachedKey, e.request, isNavigate));
});

async function respond(cachedKey, original, isNavigate) {
  const cached = await caches.match(cachedKey, { ignoreSearch: true });

  // يبدأ التحديث في الخلفية دون انتظار — فلا يؤخّر العرض.
  const updating = fetch(original)
    .then((res) => {
      if (res && res.status === 200 && res.type === "basic") {
        if (isNavigate) {
          // الصفحة نفسها: نحدّث المفتاح الذي يُخدَم منه التنقّل، وإلا بقي
          // المستخدم على نسخة قديمة للأبد (انظر الملاحظة في أعلى الملف).
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy)).catch(() => {});
        }
        const copy2 = res.clone();
        caches.open(CACHE).then((c) => c.put(original, copy2)).catch(() => {});
      }
      return res;
    })
    .catch(() => null);

  if (cached) return cached;

  const net = await updating;
  return net || new Response("Offline", {
    status: 503,
    statusText: "Offline",
    headers: { "Content-Type": "text/plain; charset=utf-8" }
  });
}
