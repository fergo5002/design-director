import sys, unittest, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import slop_lint as sl

def rules(text, name="a.tsx", **kw):
    return sorted({f.rule for f in sl.lint_text(text, name, **kw)})

class Rules(unittest.TestCase):
    def test_banned_font(self):
        self.assertIn("default-font", rules("h1 { font-family: 'Space Grotesk', sans-serif }", "a.css"))
        self.assertIn("default-font", rules("import { Inter } from 'next/font/google'"))
        self.assertNotIn("default-font", rules("h1 { font-family: 'Interstate' }", "a.css"))

    def test_purple_blue_gradient(self):
        self.assertIn("purple-blue-gradient", rules('<div className="bg-gradient-to-r from-purple-500 to-blue-500">'))
        self.assertIn("purple-blue-gradient", rules("a{background:linear-gradient(90deg,#7c3aed,#2563eb)}", "a.css"))
        self.assertNotIn("purple-blue-gradient", rules('<div className="from-stone-100 to-stone-200">'))

    def test_gradient_text(self):
        self.assertIn("gradient-text", rules('<h1 className="bg-clip-text text-transparent bg-gradient-to-r">'))

    def test_eyebrow(self):
        self.assertIn("eyebrow", rules('<p className="text-xs uppercase tracking-widest">New</p>'))
        self.assertNotIn("eyebrow", rules('<p className="text-lg">Hello</p>'))

    def test_emoji_icon(self):
        self.assertIn("emoji-icon", rules("<li>🚀 Fast deploys</li>"))

    def test_outline_none_without_focus_visible(self):
        self.assertIn("focus-removed", rules("button{outline:none}", "a.css"))
        self.assertNotIn("focus-removed", rules("button{outline:none} button:focus-visible{outline:2px solid}", "a.css"))

    def test_zoom_blocked(self):
        self.assertIn("zoom-blocked", rules('<meta name="viewport" content="width=device-width, maximum-scale=1">', "a.html"))

    def test_ai_copy(self):
        self.assertIn("ai-copy", rules("<p>Unlock seamless workflows</p>"))
        self.assertNotIn("ai-copy", rules("const unlockDoor = () => {}"))

    def test_transition_all(self):
        self.assertIn("transition-all", rules("a{transition: all .3s}", "a.css"))

    def test_default_form_control(self):
        self.assertIn("default-control", rules('<input type="range" />'))
        self.assertNotIn("default-control", rules('<input type="range" className="appearance-none" />'))

    def test_ignore_comment(self):
        self.assertNotIn("emoji-icon", rules("<li>🚀 Fast</li> {/* dd-lint-ignore emoji-icon */}"))

    def test_em_dash_is_opt_in(self):
        self.assertNotIn("em-dash", rules("<p>Fast — and cheap</p>"))
        self.assertIn("em-dash", rules("<p>Fast — and cheap</p>", enable={"em-dash"}))

class Project(unittest.TestCase):
    def test_motion_without_reduced_motion_is_flagged_once(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.css").write_text("@keyframes spin{to{transform:rotate(1turn)}}")
            found = sl.lint_paths([d])
            self.assertEqual([f.rule for f in found].count("no-reduced-motion"), 1)
            pathlib.Path(d, "b.css").write_text("@media (prefers-reduced-motion: reduce){*{animation:none}}")
            self.assertNotIn("no-reduced-motion", [f.rule for f in sl.lint_paths([d])])

    def test_skips_node_modules(self):
        with tempfile.TemporaryDirectory() as d:
            nm = pathlib.Path(d, "node_modules", "x"); nm.mkdir(parents=True)
            (nm / "a.css").write_text("a{font-family:Inter}")
            self.assertEqual(sl.lint_paths([d]), [])

class ProjectControls(unittest.TestCase):
    def test_control_styled_in_another_stylesheet_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Slider.tsx").write_text('<input type="range" className="slider" />')
            self.assertIn("default-control", [f.rule for f in sl.lint_paths([d])])
            pathlib.Path(d, "slider.css").write_text(".slider::-webkit-slider-thumb{width:20px}")
            self.assertNotIn("default-control", [f.rule for f in sl.lint_paths([d])])

    def test_markdown_is_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "notes.md").write_text("Unlock seamless value")
            self.assertEqual(sl.lint_paths([d]), [])
            self.assertIn("ai-copy", [f.rule for f in sl.lint_paths([d], md=True)])

if __name__ == "__main__":
    unittest.main()
