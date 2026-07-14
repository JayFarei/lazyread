# Listen Read reader

A private, local-first reader with fully preloaded local narration and synchronized word highlighting.

## Build and run

```sh
npm install
npm run content:prepare
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python \
  "mlx-audio @ git+https://github.com/Blaizzy/mlx-audio.git@<verified-current-commit>"
npm run generate:audio
npm test
npm run validate:audio
npm run build
npm run preview
```

The preview listens on `127.0.0.1:__LISTEN_READ_PORT__`.

