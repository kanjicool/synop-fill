/** Tailwind (standalone CLI) คอมไพล์ web/input.css -> web/app.css ด้วย script/build-css
 *  สีทุกตัวอ้าง CSS variable ใน input.css เพื่อให้ธีมสว่าง/มืดสลับตามระบบโดยไม่ต้องใช้ class dark: */
module.exports = {
  content: ["./web/index.html", "./web/app.js"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        "accent-soft": "var(--accent-soft)",
      },
      fontFamily: {
        // ใช้ฟอนต์ที่มีในเครื่อง (ระบบต้องใช้ออฟไลน์ได้ ไม่ดึงจาก Google Fonts)
        sans: ['"Leelawadee UI"', "Tahoma", '"Noto Sans Thai"', "system-ui", "sans-serif"],
        mono: ['"Cascadia Mono"', "Consolas", "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
};
