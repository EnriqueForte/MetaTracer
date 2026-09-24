/** Tailwind build config. The CLI binary is not a runtime dependency.

Content is the Jinja templates only. Tokens and components live in
metatracer.css and must not be regenerated here.
*/
module.exports = {
  content: ["./src/metatracer/api/templates/**/*.html"],
  theme: {
    extend: {},
  },
};
