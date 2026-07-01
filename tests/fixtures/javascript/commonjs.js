// CommonJS: require() + module.exports
const path = require("path");

function joinParts(a, b) {
  return path.join(a, b);
}

module.exports = { joinParts };
