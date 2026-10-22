"""اختبارات منطق الـ Hub (as3.py / as3_app.py) بلا هاردوير.

التشغيل:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import unittest

import hub_loader
import hubclock


def capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args)
    return result, buf.getvalue()


class GeneratedProgramTests(unittest.TestCase):
    """البرنامج الناتج يجب أن يكون Python صالحًا لغويًا (بلا Pybricks)."""

    def _program(self, module, with_sensors=True):
        module.actions.clear()
        module.refl.clear()
        module.refl.add(9)
        module.refl.add(90)
        if with_sensors:
            module.actions.append(("sensor", ["# LEFT sensor (Port.C): reflection=9"], None, None))
        module.actions.append(("move", [("turn", 90), ("straight", 500)], 0, 0))
        module.actions.append(("move", [("turn", -90), ("straight", 200)], 500, 90))
        module.actions.append(("move", [("find_line", (1, 260)), ("align_line", 25)], 700, 0))
        module.actions.append(("move", [("follow_line", (400, "L"))], 800, 0))
        module.actions.append(("move", [("follow_line", (-250, "R"))], 1200, 0))
        out = capture(module.print_full_program)[1]
        if "#@@PROGRAM_BEGIN@@" in out:
            out = out.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]
        return out

    def _assert_compiles(self, text):
        compile(text, "<generated>", "exec")
        self.assertIn("def run():", text)
        self.assertIn("robot.settings(straight_acceleration=", text)
        self.assertIn('follow_line(-250, "R")', text)  # الإشارة محفوظة (رجوع)

    def test_original_program_compiles(self):
        module = hub_loader.load_original()
        self._assert_compiles(self._program(module))

    def test_app_program_compiles(self):
        module = hub_loader.load_app()
        self._assert_compiles(self._program(module))

    def test_program_without_sensors_compiles(self):
        module = hub_loader.load_app()
        module.actions.clear()
        module.refl.clear()
        module.actions.append(("move", [("straight", 300)], 0, 0))
        text = capture(module.print_full_program)[1]
        text = text.split("#@@PROGRAM_BEGIN@@")[1].split("#@@PROGRAM_END@@")[0]
        compile(text, "<generated>", "exec")
        self.assertNotIn("ColorSensor(Port.C)", text)   # لا نضيف حساسات بلا داعٍ


class ThresholdTests(unittest.TestCase):
    """عتبة الخط تُحسب من العدّادين بدل قائمة العينات (توفير ذاكرة)."""

    def test_needs_a_clear_gap(self):
        module = hub_loader.load_app()
        module.refl.clear()
        for v in (80, 85, 82):
            module.refl.add(v)
        self.assertIsNone(module.estimated_threshold())

    def test_midpoint_of_min_and_max(self):
        module = hub_loader.load_app()
        module.refl.clear()
        for v in (88, 12, 90, 9, 70):
            module.refl.add(v)
        self.assertEqual(module.refl.lo, 9)
        self.assertEqual(module.refl.hi, 90)
        self.assertEqual(module.estimated_threshold(), 49)

    def test_collects_only_when_moving(self):
        module = hub_loader.load_app()
        module.refl.clear()
        module.sample_sensors(False)      # سكون: لا تُحسب
        self.assertEqual(module.refl.n, 0)
        module.sample_sensors(True)       # حركة: تُحسب
        self.assertEqual(module.refl.n, 1)


class CodeReceiveTests(unittest.TestCase):
    """آلة استلام الكود K … E: الحالات الحدّية التي كانت تُعلّق الـ Hub."""

    LINES = ["T -90", "S 500", "F 1 250", "A 25", "L 400 L", "L 300 R", "S -120"]

    def _wire(self, lines):
        return "K" + "".join(line + "\n" for line in lines) + "E"

    def test_roundtrip(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, self._wire(self.LINES))
        self.assertFalse(m.code_mode)
        self.assertEqual([seg[0] for seg in m.run_queue],
                         ["turn", "straight", "find_line", "align_line",
                          "follow_line", "follow_line", "straight"])
        self.assertEqual(m.run_queue[0], ("turn", -90))
        self.assertEqual(m.run_queue[5], ("follow_line", 300, "R"))
        self.assertEqual(m.code_skipped, 0)

    def test_e_finishes_even_mid_line(self):
        # كان E يُقبل فقط في بداية سطر؛ لو ضاع \n يبقى الهاب عالقًا للأبد
        m = hub_loader.load_app()
        hub_loader.feed(m, "K" + "T 90\n" + "S 400" + "E")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("turn", 90), ("straight", 400)])

    def test_long_line_is_dropped_not_truncated(self):
        # قصّ "S 4000" إلى "S 400" ينفّذ أمرًا خاطئًا — يجب تجاهل السطر كله
        m = hub_loader.load_app()
        long_line = "S " + "1" * 40
        hub_loader.feed(m, self._wire(["T 45", long_line, "S 250"]))
        self.assertEqual(m.run_queue, [("turn", 45), ("straight", 250)])
        self.assertEqual(m.code_skipped, 1)

    def test_duplicate_e_is_harmless(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "KT 30\nEE")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("turn", 30)])

    def test_timeout_leaves_previous_code_untouched(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 111)]
        hub_loader.feed(m, "KT 30\n")
        self.assertTrue(m.code_mode)
        hubclock.advance(m.CODE_TIMEOUT_MS + 1)
        # نفس الفحص الموجود في الحلقة الرئيسية
        if m.code_mode and m.code_watch.time() > m.CODE_TIMEOUT_MS:
            m.code_receive_abort("مهلة")
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("straight", 111)])

    def test_empty_submission_keeps_previous_code(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 222)]
        hub_loader.feed(m, "KE")
        self.assertEqual(m.run_queue, [("straight", 222)])

    def test_threshold_command_sets_run_threshold(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "H 57\n")
        self.assertEqual(m.run_th, 57)
        # H أمر سطر واحد: يجب أن يعود الـ Hub جاهزًا، وإلا ابتلع G التالي
        self.assertFalse(m.code_mode)
        hub_loader.feed(m, "H 999\n")
        self.assertEqual(m.run_th, m.TH_MAX)     # يُقصّ إلى النطاق الآمن

    def test_threshold_then_go_starts_run(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "KT 30\nE")
        m.run_queue = [("turn", 30)]
        hub_loader.feed(m, "H 61\nG")
        self.assertTrue(m.run_active)
        self.assertEqual(m.run_th, 61)

    def test_threshold_survives_start(self):
        m = hub_loader.load_app()
        hub_loader.feed(m, "H 57\n")
        m.run_queue = [("straight", 100)]
        m.run_active = False
        _, out = capture(m.run_start)
        self.assertEqual(m.run_th, 57)          # لا تُستبدل بالمحسوبة في G
        self.assertIn("عتاة الخط = 57", out)
        self.assertTrue(m.run_active)

    def test_run_limit_guards_memory(self):
        m = hub_loader.load_app()
        lines = ["S 10"] * (m.RUN_MAX_LINES + 5)
        hub_loader.feed(m, self._wire(lines))
        self.assertEqual(len(m.run_queue), m.RUN_MAX_LINES)
        self.assertEqual(m.code_skipped, 5)


class BulkReceiveTests(unittest.TestCase):
    """الوضع السريع: B + حزم N (بايتان طول + حمولة) + E.

    التطبيق يرسل البرنامج كاملًا في 10–20 حزمة بدل ~900 كتابة حرف واحد،
    والأسطر قد تنقسم بين حزمتين — لهذا تُختبر هنا حدود الحزم.
    """

    PAYLOAD = "T -90\nS 500\nF 1 250\nA 25\nL 400 L\nS -120\n"

    def _frames(self, text, size):
        out = "B"
        for i in range(0, len(text), size):
            chunk = text[i:i + size]
            out += "N" + chr(len(chunk) & 0xFF) + chr(len(chunk) >> 8) + chunk
        return out + "E"

    def _run(self, size):
        m = hub_loader.load_app()
        hub_loader.feed(m, self._frames(self.PAYLOAD, size))
        return m

    def test_split_frames_anywhere(self):
        for size in (1, 5, 13, 90):
            with self.subTest(size=size):
                m = self._run(size)
                self.assertFalse(m.code_mode)
                self.assertEqual(
                    [seg[0] for seg in m.run_queue],
                    ["turn", "straight", "find_line", "align_line",
                     "follow_line", "straight"],
                )
                self.assertEqual(m.code_skipped, 0)

    def test_oversized_frame_aborts(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 77)]
        big = m.FRAME_MAX + 1
        hub_loader.feed(m, "BN" + chr(big & 0xFF) + chr(big >> 8))
        self.assertFalse(m.code_mode)
        self.assertEqual(m.run_queue, [("straight", 77)])

    def test_bulk_then_legacy_still_works(self):
        m = hub_loader.load_app()
        frame = "T 15\n"
        hub_loader.feed(m, "B" + "N" + chr(len(frame)) + chr(0) + frame + "E")
        self.assertEqual(m.run_queue, [("turn", 15)])
        hub_loader.feed(m, "KS 20\nE")
        self.assertEqual(m.run_queue, [("straight", 20)])


class RecordingTests(unittest.TestCase):
    def test_action_limit_keeps_tracking_point(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.MAX_ACTIONS = 2
        for _ in range(3):
            m.push_action("move", [("straight", 100)], 0, 0)
        self.assertEqual(len(m.actions), 2)

    def test_follow_line_keeps_backwards_sign(self):
        m = hub_loader.load_app()
        m.actions.clear()
        m.last_distance = 500
        m.robot.distance_value = 300          # رجع 200 مم
        m.do_follow_line_seg()
        segs = m.actions[-1][1]
        self.assertEqual(segs, [("follow_line", (-200, "L"))])


class ExecutionTests(unittest.TestCase):
    def test_cancel_brakes_instead_of_coasting(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        m.run_active = True
        m.run_cancel("اختبار")
        self.assertEqual(m.robot.braked, 1)
        self.assertFalse(m.run_active)

    def test_heartbeat_cancels_when_app_goes_silent(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        hub_loader.feed(m, "p")               # التطبيق بدأ يرسل نبضات
        m.beat_on = True
        m.run_active = True
        hubclock.advance(m.HEARTBEAT_MS + 1)
        _, out = capture(m.run_tick)
        self.assertFalse(m.run_active)
        self.assertIn("انقطاع الاتصال", out)

    def test_heartbeat_off_keeps_running(self):
        m = hub_loader.load_app()
        m.run_queue = [("straight", 1000)]
        m.run_active = True
        m.run_speed = m.RUN_FOLLOW_SPEED
        hubclock.advance(m.HEARTBEAT_MS * 5)
        m.run_tick()
        self.assertTrue(m.run_active)


if __name__ == "__main__":
    unittest.main()
