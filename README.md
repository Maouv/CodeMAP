# CodeMAP

Interactive visual dependency graph for Python codebases. Scans a directory of `.py` files, builds a dependency + risk graph, and serves an interactive D3 + Canvas2D visualization on `http://localhost:8765`.

## Install

```bash
pip install codemap
# with optional AI summaries:
pip install "codemap[anthropic]"
pip install "codemap[openai]"
pip install "codemap[ai]"
```

## Usage

```bash
codemap ./src
codemap ./src --port 8080 --no-browser
codemap ./src --ai-provider anthropic
```

Open `http://localhost:8765` in your browser.

## License

MIT — see [LICENSE](LICENSE).
