// Bridge so pytest can call the page's JS modules: reads {fn, args} JSON on stdin.
const path = require("path");
const P = require(path.join(__dirname, "..", "site", "parser.js"));
const L = require(path.join(__dirname, "..", "site", "lookthrough.js"));
let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  const req = JSON.parse(input);
  let out;
  if (req.fn === "parse") {
    const map = req.map || require(path.join(__dirname, "..", "site", "tickers.json")).t;
    out = P.parse(req.text, map);
  } else if (req.fn === "lookthrough") {
    out = L.compute(req.args);
  } else if (req.fn === "resolve") {
    out = P.resolve(req.item, req.choice);
  }
  process.stdout.write(JSON.stringify(out));
});
