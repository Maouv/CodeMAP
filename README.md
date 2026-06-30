# graps

Interactive visual dependency graph for Python codebases. Scans a directory of `.py` files, builds a dependency + risk graph, and serves an interactive D3 + Canvas2D visualization on `http://localhost:8765`.

## Install

```bash
pip install graps
# with optional AI summaries:
pip install "graps[anthropic]"
pip install "graps[openai]"
pip install "graps[ai]"
```

## Usage

```bash
graps ./src
graps ./src --port 8080 --no-browser
graps ./src --ai-provider anthropic
```

Open `http://localhost:8765` in your browser.

## License

MIT — see [LICENSE](LICENSE).
