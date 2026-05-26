const fs = require("fs");
const path = require("path");

function checkFile(filePath) {
  const code = fs.readFileSync(filePath, "utf8");
  const parenStack = [];
  const bracketStack = [];
  const braceStack = [];
  let inString = null;
  let escaped = false;
  let tripleQuote = null;

  for (let i = 0; i < code.length; i++) {
    const ch = code[i];
    const next2 = code.slice(i, i + 3);

    if (tripleQuote) {
      if (next2 === tripleQuote) {
        tripleQuote = null;
        i += 2;
      }
      continue;
    }

    if (!inString) {
      if (next2 === '"""' || next2 === "'''") {
        tripleQuote = next2;
        i += 2;
        continue;
      }
      if (ch === '"' || ch === "'") {
        inString = ch;
        continue;
      }
      if (ch === '(') parenStack.push(i);
      else if (ch === ')') {
        if (!parenStack.length) {
          console.error(`MISMATCHED PAREN at ${filePath} pos ${i}`);
          return false;
        }
        parenStack.pop();
      }
      else if (ch === '[') bracketStack.push(i);
      else if (ch === ']') {
        if (!bracketStack.length) {
          console.error(`MISMATCHED BRACKET at ${filePath} pos ${i}`);
          return false;
        }
        bracketStack.pop();
      }
      else if (ch === '{') braceStack.push(i);
      else if (ch === '}') {
        if (!braceStack.length) {
          console.error(`MISMATCHED BRACE at ${filePath} pos ${i}`);
          return false;
        }
        braceStack.pop();
      }
    } else {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === '\\') {
        escaped = true;
        continue;
      }
      if (ch === inString) {
        inString = null;
      }
    }
  }

  if (parenStack.length || bracketStack.length || braceStack.length || inString || tripleQuote) {
    console.error(`UNBALANCED at ${filePath}`);
    return false;
  }
  return true;
}

function walk(dir) {
  let ok = true;
  for (const entry of fs.readdirSync(dir)) {
    const full = path.join(dir, entry);
    const st = fs.statSync(full);
    if (st.isDirectory()) {
      ok = walk(full) && ok;
    } else if (full.endsWith('.py')) {
      if (!checkFile(full)) ok = false;
    }
  }
  return ok;
}

const ok = walk('src') && walk('tests');
if (ok) console.log('All Python files passed basic syntax checks');
process.exit(ok ? 0 : 1);
