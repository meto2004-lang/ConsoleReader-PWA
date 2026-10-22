// اختبارات منطق التطبيق (JS) — تعمل بلا متصفح ولا روبوت.
// التشغيل:  node --test tests/web.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "app/index.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// نستخرج الدوال النقية فقط من داخل الصفحة (النص كله يعتمد على DOM).
function slice(from, to) {
  const start = script.indexOf(from);
  const end = script.indexOf(to, start);
  assert.ok(start >= 0 && end > start, "لم أجد الدالة " + from);
  return script.slice(start, end);
}

const pure = [
  slice("const progNum", "function setSendBusy"),
  slice("const FRAME_MAX", "async function sendProgramToRobot"),
].join("\n");
const api = new Function(pure + "\nreturn { programToRobotLines, programThreshold, buildFrames, FRAME_MAX };")();

const PROGRAM = `from pybricks.hubs import PrimeHub
robot = DriveBase(left_motor, right_motor, 62.4, 110)
LINE_THRESHOLD = 49  # محسوبة من قياساتك

def find_line(direction=1, max_dist=250, speed=80):
    robot.reset()
    robot.drive(direction * speed, 0)
    while abs(robot.distance()) < max_dist:
        robot.stop()
        return False
    robot.stop()
    return False

def run():
    robot.turn(-90)
    robot.straight(500)
    find_line(1, 250)
    align_on_line(25)
    follow_line(400, "L")
    follow_line(-250, side="R")
    robot.stop()          # غير مدعوم — يُتجاهل

run()
`;

test("يحوّل run() فقط ويتجاهل أجسام الدوال المساعدة", () => {
  const { lines, skipped } = api.programToRobotLines(PROGRAM);
  assert.deepEqual(lines, ["T -90", "S 500", "F 1 250", "A 25", "L 400 L", "L -250 R"]);
  // الأجسام الداخلية ليست «أسطرًا متجاهلة» — كان العدد 9 كإنذار كاذب
  assert.deepEqual(skipped, ["robot.stop()"]);
});

test("يقرأ عتبة الخط من اللوحة", () => {
  assert.equal(api.programThreshold(PROGRAM), 49);
  assert.equal(api.programThreshold("robot.straight(100)"), null);
});

test("يبني حزمًا بحجم آمن ويعيد تجميع النص نفسه", () => {
  const text = PROGRAM.split("\n").filter(l => /^(robot\.|find_line|follow_line)/.test(l.trim())).join("\n");
  const frames = api.buildFrames(text, 17);
  const decoder = new TextDecoder();
  let rebuilt = "";
  for (const f of frames) {
    assert.equal(f[0], 78);                       // 'N'
    const len = f[1] | (f[2] << 8);
    assert.equal(len, f.length - 3);
    assert.ok(f.length <= api.FRAME_MAX + 3);     // لا تتجاوز حدّ خاصية BLE
    rebuilt += decoder.decode(f.subarray(3));
  }
  assert.equal(rebuilt, text);
});

test("حزمة واحدة لكل 90 بايت كحد أقصى", () => {
  const frames = api.buildFrames("x".repeat(1000));
  assert.equal(frames.length, 12);
  assert.ok(frames.every(f => f.length <= 93));
});
